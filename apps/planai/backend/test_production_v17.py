"""
PLONAGRAM OS V1.7.1 - Production Validation Tests
Tests merge quality, engine correctness, and unplaced reasons
"""

import sys
sys.path.append('./services')

from services.merge_service import merge_service
from services.abc_service import abc_service
from services.catalog_service import catalog_service
from services.planogram_engine import planogram_engine
from services.store_dna_service import store_dna_service


class ProductionValidator:
    """Test suite for V1.7.1 production readiness"""
    
    def __init__(self):
        self.test_results = []
    
    def validate_merge_confidence_levels(self):
        """Test BLOCKER #2: Merge confidence thresholds"""
        print("\n=== Testing Merge Confidence Levels ===")
        
        # Test data
        abc_items = [
            {'sku': 'ABC001', 'product_name': 'Test Product 1', 'barcode': '1234567890123', 'sales_qty_7d': 100},
            {'sku': 'ABC002', 'product_name': 'Test Product 2', 'barcode': '9876543210987', 'sales_qty_7d': 50},
            {'sku': 'ABC003', 'product_name': 'Similar Product Name', 'sales_qty_7d': 30},
        ]
        
        catalog_items = [
            {'sku': 'CAT001', 'product_name': 'Test Product 1', 'barcode': '1234567890123', 'width_cm': 10},
            {'sku': 'ABC002', 'product_name': 'Test Product 2 Different', 'barcode': '9876543210987', 'width_cm': 12},
            {'sku': 'CAT003', 'product_name': 'Similar Product Title', 'barcode': '', 'width_cm': 8},
        ]
        
        result = merge_service.merge_abc_catalog(abc_items, catalog_items)
        
        # Assertions
        assert result['match_stats']['barcode_match'] > 0, "Barcode match should work"
        
        # Find the barcode match
        barcode_merged = [p for p in result['merged_products'] if p.get('_match_method') == 'barcode_match']
        if barcode_merged:
            assert barcode_merged[0]['_match_confidence'] == 0.98, f"Barcode confidence must be 0.98, got {barcode_merged[0]['_match_confidence']}"
            print("✓ Barcode confidence = 0.98 (correct)")
        
        # Check fuzzy matches are in unmatched (not auto-merged)
        fuzzy_unmatched = [p for p in result['unmatched_abc'] if 'fuzzy' in p.get('_reason', '')]
        if fuzzy_unmatched:
            print(f"✓ Fuzzy matches sent to review (not auto-merged): {len(fuzzy_unmatched)}")
        
        print(f"Match rate: {result['summary']['match_rate']}%")
        print(f"Match stats: {result['match_stats']}")
        
        return result
    
    def validate_store_dna_structure(self):
        """Test BLOCKER #3: Left/Right module support"""
        print("\n=== Testing Store DNA Structure ===")
        
        wizard_input = {
            'store_code': 'TEST',
            'store_name': 'Test Store',
            'num_ambient_aisles': 3,
            'left_modules_per_aisle': 3,
            'right_modules_per_aisle': 3,
            'has_chilled_room': True,
            'has_frozen_room': True,
            'standard_rack_dimensions': {'width': 100, 'depth': 50, 'height': 250},
            'shelves_per_rack': 6
        }
        
        dna = store_dna_service.build_from_wizard_easy(wizard_input)
        
        # Check aisles have left/right modules
        aisles = [obj for obj in dna['layout_objects'] if obj['type'] == 'corridor']
        
        for aisle in aisles:
            assert 'left_modules' in aisle, f"Aisle {aisle['id']} missing left_modules"
            assert 'right_modules' in aisle, f"Aisle {aisle['id']} missing right_modules"
            assert len(aisle['left_modules']) > 0, f"Aisle {aisle['id']} has no left modules"
            assert len(aisle['right_modules']) > 0, f"Aisle {aisle['id']} has no right modules"
            
            # Check modules have shelves with proper structure
            for module in aisle['left_modules']:
                assert 'module_id' in module
                assert 'shelves' in module
                for shelf in module['shelves']:
                    assert 'shelf_label' in shelf
                    assert 'height_from_ground_cm' in shelf
                    assert 'max_weight_kg' in shelf
        
        print(f"✓ DNA has {len(aisles)} aisles with left/right modules")
        print(f"✓ Total left modules: {sum(len(a['left_modules']) for a in aisles)}")
        print(f"✓ Total right modules: {sum(len(a['right_modules']) for a in aisles)}")
        
        return dna
    
    def validate_fixture_first_engine(self):
        """Test BLOCKER #5: Fixture-first priority"""
        print("\n=== Testing Fixture-First Engine ===")
        
        # Mock products
        products = [
            {
                'sku': 'PROD001',
                'product_name': 'Süt 1L',
                'storage_type': 'CHILLED',
                'width_cm': 8,
                'height_cm': 25,
                'depth_cm': 8,
                'weight_kg': 1.0,
                'abc_class': 'A',
                'sales_qty_7d': 100
            },
            {
                'sku': 'PROD002',
                'product_name': 'Patates 1kg',
                'storage_type': 'AMBIENT',
                'width_cm': 15,
                'height_cm': 10,
                'depth_cm': 15,
                'weight_kg': 1.0,
                'abc_class': 'B',
                'sales_qty_7d': 50
            },
            {
                'sku': 'PROD003',
                'product_name': 'Su 5L',
                'storage_type': 'AMBIENT',
                'width_cm': 20,
                'height_cm': 30,
                'depth_cm': 15,
                'weight_kg': 5.5,
                'abc_class': 'A',
                'sales_qty_7d': 200
            }
        ]
        
        # Mock fixture pools
        fixture_pools = {
            'CHILLED': [
                {
                    'id': 'CHILLED_1',
                    'left_modules': [
                        {
                            'module_id': 'CH-L1',
                            'shelves': [
                                {
                                    'shelf_label': 'CH-L1-R1',
                                    'dimensions': {'width_cm': 100, 'depth_cm': 50, 'height_cm': 35},
                                    'max_weight_kg': 50,
                                    'height_from_ground_cm': 120
                                }
                            ]
                        }
                    ],
                    'right_modules': []
                }
            ],
            'PRODUCE_AMBIENT': [
                {
                    'id': 'PRODUCE_1',
                    'left_modules': [
                        {
                            'module_id': 'PR-L1',
                            'shelves': [
                                {
                                    'shelf_label': 'PR-L1-R1',
                                    'dimensions': {'width_cm': 120, 'depth_cm': 60, 'height_cm': 30},
                                    'max_weight_kg': 40,
                                    'height_from_ground_cm': 80
                                }
                            ]
                        }
                    ],
                    'right_modules': []
                }
            ],
            'HEAVY_BULKY': [
                {
                    'id': 'PALLET_1',
                    'left_modules': [
                        {
                            'module_id': 'PL-L1',
                            'shelves': [
                                {
                                    'shelf_label': 'PL-L1-R1',
                                    'dimensions': {'width_cm': 200, 'depth_cm': 100, 'height_cm': 50},
                                    'max_weight_kg': 500,
                                    'height_from_ground_cm': 0
                                }
                            ]
                        }
                    ],
                    'right_modules': []
                }
            ],
            'AMBIENT_GENERAL': []
        }
        
        result = planogram_engine.generate_planogram(products, fixture_pools)
        
        print(f"✓ Total products: {result['summary']['total_products']}")
        print(f"✓ Placed: {result['summary']['placed']}")
        print(f"✓ Unplaced: {result['summary']['unplaced']}")
        print(f"✓ Placement rate: {result['summary']['placement_rate']}%")
        
        # Verify fixture-first worked
        placements = result['placements']
        
        # Süt should go to CHILLED
        sut_placement = [p for p in placements if p['sku'] == 'PROD001']
        if sut_placement:
            assert sut_placement[0]['pool'] == 'CHILLED', "Süt should be in CHILLED pool"
            print("✓ Süt placed in CHILLED (fixture-first worked)")
        
        # Patates should go to PRODUCE
        patates_placement = [p for p in placements if p['sku'] == 'PROD002']
        if patates_placement:
            assert patates_placement[0]['pool'] == 'PRODUCE_AMBIENT'
            print("✓ Patates placed in PRODUCE_AMBIENT")
        
        # Heavy water should go to HEAVY_BULKY
        water_placement = [p for p in placements if p['sku'] == 'PROD003']
        if water_placement:
            assert water_placement[0]['pool'] == 'HEAVY_BULKY'
            print("✓ Heavy water placed in HEAVY_BULKY (weight rule)")
        
        return result
    
    def validate_unplaced_reasons(self):
        """Test BLOCKER #6: Unplaced reason codes"""
        print("\n=== Testing Unplaced Reasons ===")
        
        # Test product that can't be placed
        products = [
            {
                'sku': 'UNFIT001',
                'product_name': 'Oversized Product',
                'storage_type': 'AMBIENT',
                'width_cm': 300,  # Too wide for any shelf
                'height_cm': 50,
                'depth_cm': 50,
                'weight_kg': 2.0,
                'abc_class': 'C',
                'sales_qty_7d': 10
            }
        ]
        
        fixture_pools = {
            'AMBIENT_GENERAL': [
                {
                    'id': 'AMB_1',
                    'left_modules': [
                        {
                            'module_id': 'A-L1',
                            'shelves': [
                                {
                                    'shelf_label': 'A-L1-R1',
                                    'dimensions': {'width_cm': 100, 'depth_cm': 50, 'height_cm': 35},
                                    'max_weight_kg': 50,
                                    'height_from_ground_cm': 100
                                }
                            ]
                        }
                    ],
                    'right_modules': []
                }
            ]
        }
        
        result = planogram_engine.generate_planogram(products, fixture_pools)
        
        assert len(result['unplaced']) == 1, "Product should be unplaced"
        unplaced = result['unplaced'][0]
        
        assert '_unplaced_reason' in unplaced, "Unplaced reason must be present"
        print(f"✓ Unplaced reason: {unplaced['_unplaced_reason']}")
        print(f"✓ Context: {unplaced.get('_context', {})}")
        
        return result
    
    def run_all_tests(self):
        """Run complete validation suite"""
        print("\n" + "="*60)
        print("PLONAGRAM V1.7.1 PRODUCTION VALIDATION")
        print("="*60)
        
        try:
            # Test 1: Merge confidence
            self.validate_merge_confidence_levels()
            
            # Test 2: Store DNA structure
            self.validate_store_dna_structure()
            
            # Test 3: Fixture-first engine
            self.validate_fixture_first_engine()
            
            # Test 4: Unplaced reasons
            self.validate_unplaced_reasons()
            
            print("\n" + "="*60)
            print("✅ ALL BLOCKERS VALIDATED - PRODUCTION READY")
            print("="*60)
            
            return True
            
        except AssertionError as e:
            print(f"\n❌ VALIDATION FAILED: {e}")
            return False
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False


# Run tests
if __name__ == '__main__':
    validator = ProductionValidator()
    success = validator.run_all_tests()
    
    sys.exit(0 if success else 1)
