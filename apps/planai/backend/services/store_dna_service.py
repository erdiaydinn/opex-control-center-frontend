"""
PLONAGRAM OS - Store DNA Service
Handles warehouse layout definition, validation, wizard flows
"""

from typing import Dict, List, Tuple, Any, Optional
import json
from datetime import datetime


class StoreDNAService:
    """Store DNA management and validation"""
    
    REQUIRED_FIELDS = ['store_code', 'store_name', 'layout_objects', 'fixture_summary']
    
    FIXTURE_TYPES = {
        'steel_rack': {'family': 'rack', 'planogram_eligible': True},
        'hdr_heavy_rack': {'family': 'heavy_rack', 'planogram_eligible': True},
        'martek_plus4': {'family': 'cooler', 'planogram_eligible': True},
        'martek_frozen_minus18': {'family': 'freezer', 'planogram_eligible': True},
        'ice_cream_chest_freezer_small': {'family': 'chest_freezer', 'planogram_eligible': True},
        'ice_cream_chest_freezer_medium': {'family': 'chest_freezer', 'planogram_eligible': True},
        'ice_cream_chest_freezer_large': {'family': 'chest_freezer', 'planogram_eligible': True},
        'vertical_chiller': {'family': 'cooler', 'planogram_eligible': True},
        'produce_shelf': {'family': 'produce', 'planogram_eligible': True},
        'horizontal_fridge': {'family': 'horizontal_cooler', 'planogram_eligible': True},
        'corridor': {'family': 'structure', 'planogram_eligible': True},
        'chilled_room': {'family': 'room', 'planogram_eligible': True},
        'frozen_room': {'family': 'room', 'planogram_eligible': True},
        'column': {'family': 'structure', 'planogram_eligible': False},
        'wall': {'family': 'structure', 'planogram_eligible': False},
        'dispatch': {'family': 'zone', 'planogram_eligible': False},
        'receiving': {'family': 'zone', 'planogram_eligible': False},
    }
    
    def validate_dna(self, dna: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate Store DNA structure
        Returns: (is_valid, error_messages)
        """
        errors = []
        
        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in dna:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # Validate layout objects
        layout_objects = dna.get('layout_objects', [])
        if not layout_objects:
            errors.append("layout_objects cannot be empty")
            return False, errors
        
        for idx, obj in enumerate(layout_objects):
            if 'id' not in obj:
                errors.append(f"Object {idx} missing 'id'")
            if 'type' not in obj:
                errors.append(f"Object {idx} missing 'type'")
            if 'x' not in obj or 'y' not in obj:
                errors.append(f"Object {idx} missing position (x, y)")
            if 'w' not in obj or 'd' not in obj or 'h' not in obj:
                errors.append(f"Object {idx} missing dimensions (w, d, h)")
        
        # Validate fixture summary
        fixture_summary = dna.get('fixture_summary', {})
        if not isinstance(fixture_summary, dict):
            errors.append("fixture_summary must be a dict")
        
        return len(errors) == 0, errors
    
    def build_from_wizard_easy(self, wizard_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Store DNA from Easy Setup wizard
        
        wizard_input:
            store_code: str
            store_name: str
            warehouse_size: 'small' | 'medium' | 'large'
            num_ambient_aisles: int
            has_chilled_room: bool
            has_frozen_room: bool
            has_algida_fridge: bool
            standard_rack_dimensions: {width, depth, height}
            shelves_per_rack: int
        """
        store_code = wizard_input['store_code']
        store_name = wizard_input['store_name']
        num_aisles = wizard_input.get('num_ambient_aisles', 6)
        has_chilled = wizard_input.get('has_chilled_room', True)
        has_frozen = wizard_input.get('has_frozen_room', True)
        has_algida = wizard_input.get('has_algida_fridge', False)
        algida_count = max(0, int(wizard_input.get('algida_count', 1 if has_algida else 0) or 0))
        horizontal_fridge_count = max(0, int(wizard_input.get('horizontal_fridge_count', wizard_input.get('horizontal_count', 1 if wizard_input.get('has_horizontal_fridge', False) else 0)) or 0))
        martek_plus4_count = max(0, int(wizard_input.get('martek_plus4_count', wizard_input.get('vertical_chiller_count', 0)) or 0))
        
        rack_dims = wizard_input.get('standard_rack_dimensions', {
            'width': 100, 'depth': 50, 'height': 250
        })
        shelves_per_rack = int(wizard_input.get('shelves_per_rack', 6) or 6)
        left_modules_per_aisle = int(
            wizard_input.get('left_modules_per_aisle', wizard_input.get('left_modules', 3)) or 0
        )
        right_modules_per_aisle = int(
            wizard_input.get('right_modules_per_aisle', wizard_input.get('right_modules', 3)) or 0
        )
        left_fixture_type = wizard_input.get('left_fixture_type', 'steel_rack')
        right_fixture_type = wizard_input.get('right_fixture_type', 'steel_rack')

        layout_objects = []
        
        # 1. Receiving area
        layout_objects.append({
            'id': 'RECEIVING',
            'label': 'MAL KABUL',
            'type': 'receiving',
            'zone': 'INBOUND',
            'x': 6, 'y': 5, 'w': 20, 'd': 12, 'h': 3.5,
            'rotation': 0,
            'modules': 0,
            'shelves': 0
        })
        
        # 2. Ambient aisles (A, B, C, D, E, F, etc.) with LEFT and RIGHT modules
        aisle_labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        x_start = 12
        y_positions = [24, 47, 70]  # 3 rows
        
        for i in range(num_aisles):
            aisle_label = aisle_labels[i] if i < len(aisle_labels) else f'A{i}'
            row = i // 3
            col = i % 3
            
            x = x_start + col * 38
            y = y_positions[row] if row < len(y_positions) else 24 + row * 23
            
            # Build aisle with left and right modules
            aisle_obj = {
                'id': aisle_label,
                'label': aisle_label,
                'type': 'corridor',
                'zone': 'AMBIENT',
                'x': x, 'y': y, 'w': 30, 'd': 8, 'h': 2.5,
                'rotation': 0,
                'left_modules': [],
                'right_modules': [],
            }
            
            # Generate left side modules
            for m in range(left_modules_per_aisle):
                module_id = f"{aisle_label}-L{m+1}"
                aisle_obj['left_modules'].append({
                    'module_id': module_id,
                    'module_position': m + 1,
                    'fixture_type': left_fixture_type,
                    'fixture_family': self.FIXTURE_TYPES.get(left_fixture_type, {}).get('family', 'rack'),
                    'dimensions': rack_dims,
                    'shelves': [
                        {
                            'shelf_no': s + 1,
                            'shelf_label': f"{module_id}-R{s+1}",
                            'height_from_ground_cm': 25 + (s * 40),
                            'dimensions': {
                                'width_cm': rack_dims['width'],
                                'depth_cm': rack_dims['depth'],
                                'height_cm': 35
                            },
                            'allowed_storage_type': ['AMBIENT'],
                            'max_weight_kg': 45,
                        }
                        for s in range(shelves_per_rack)
                    ],
                    'total_shelves': shelves_per_rack,
                })
            
            # Generate right side modules
            for m in range(right_modules_per_aisle):
                module_id = f"{aisle_label}-R{m+1}"
                aisle_obj['right_modules'].append({
                    'module_id': module_id,
                    'module_position': m + 1,
                    'fixture_type': right_fixture_type,
                    'fixture_family': self.FIXTURE_TYPES.get(right_fixture_type, {}).get('family', 'rack'),
                    'dimensions': rack_dims,
                    'shelves': [
                        {
                            'shelf_no': s + 1,
                            'shelf_label': f"{module_id}-R{s+1}",
                            'height_from_ground_cm': 25 + (s * 40),
                            'dimensions': {
                                'width_cm': rack_dims['width'],
                                'depth_cm': rack_dims['depth'],
                                'height_cm': 35
                            },
                            'allowed_storage_type': ['AMBIENT'],
                            'max_weight_kg': 45,
                        }
                        for s in range(shelves_per_rack)
                    ],
                    'total_shelves': shelves_per_rack,
                })
            
            aisle_obj['modules'] = len(aisle_obj['left_modules']) + len(aisle_obj['right_modules'])
            aisle_obj['shelves'] = aisle_obj['modules'] * shelves_per_rack
            layout_objects.append(aisle_obj)
        
        # 3. Chilled room
        if has_chilled:
            layout_objects.append({
                'id': 'CHILLED_ROOM',
                'label': '+4 SOĞUK ODA',
                'type': 'chilled_room',
                'zone': 'CHILLED',
                'x': 108, 'y': 5, 'w': 22, 'd': 14, 'h': 3.2,
                'rotation': 0,
                'modules': 4,
                'shelves': 20,
                'temperature_c': 4
            })
        
        # 4. Frozen room
        if has_frozen:
            layout_objects.append({
                'id': 'FROZEN_ROOM',
                'label': '-18 DONUK ODA',
                'type': 'frozen_room',
                'zone': 'FROZEN',
                'x': 108, 'y': 68, 'w': 22, 'd': 16, 'h': 3.2,
                'rotation': 0,
                'modules': 4,
                'shelves': 16,
                'temperature_c': -18
            })
        
        # 5. Algida fridges - adet gerçek Store DNA'da ayrı ayrı tutulur
        if has_algida and algida_count:
            for i in range(algida_count):
                layout_objects.append({
                    'id': f'ALGIDA_{i+1}',
                    'label': f'ALGIDA DOLABI {i+1}',
                    'type': 'ice_cream_chest_freezer_medium',
                    'zone': 'FROZEN',
                    'x': 9 + (i % 5) * 8, 'y': 86 + (i // 5) * 8, 'w': 6, 'd': 3.5, 'h': 2.1,
                    'rotation': 0,
                    'modules': 1,
                    'shelves': 4,
                    'temperature_c': -18,
                    'left_modules': [{
                        'module_id': f'ALGIDA-{i+1}-M1',
                        'module_position': 1,
                        'fixture_type': 'ice_cream_chest_freezer_medium',
                        'fixture_family': 'chest_freezer',
                        'dimensions': {'width': 120, 'depth': 70, 'height': 110},
                        'shelves': [
                            {'shelf_no': s + 1, 'shelf_label': f'ALGIDA-{i+1}-R{s+1}', 'height_from_ground_cm': 10 + (s * 24), 'dimensions': {'width_cm': 120, 'depth_cm': 70, 'height_cm': 22}, 'allowed_storage_type': ['FROZEN'], 'max_weight_kg': 45}
                            for s in range(4)
                        ],
                        'total_shelves': 4,
                    }],
                    'right_modules': []
                })
        
        # 5b. Produce shelf / kasa rafı
        if wizard_input.get('has_produce_shelf', False):
            produce_modules = int(wizard_input.get('produce_module_count', 4) or 4)
            layout_objects.append({
                'id': 'PRODUCE_AMBIENT',
                'label': 'MEYVE SEBZE RAFI',
                'type': 'produce_shelf',
                'zone': 'AMBIENT',
                'x': 6, 'y': 72, 'w': 24, 'd': 6, 'h': 1.8,
                'rotation': 0,
                'modules': produce_modules,
                'shelves': produce_modules * 4,
                'left_modules': [
                    {
                        'module_id': f'PROD-L{i+1}',
                        'module_position': i + 1,
                        'fixture_type': 'produce_shelf',
                        'fixture_family': 'produce',
                        'dimensions': {'width': 120, 'depth': 60, 'height': 180},
                        'shelves': [
                            {
                                'shelf_no': s + 1,
                                'shelf_label': f'PROD-L{i+1}-R{s+1}',
                                'height_from_ground_cm': 15 + (s * 35),
                                'dimensions': {'width_cm': 120, 'depth_cm': 60, 'height_cm': 30},
                                'allowed_storage_type': ['AMBIENT'],
                                'max_weight_kg': 60,
                            } for s in range(4)
                        ],
                        'total_shelves': 4,
                    } for i in range(produce_modules)
                ],
                'right_modules': []
            })

        # 5c. Horizontal fridge / yatay dolap - adet bazlı
        if horizontal_fridge_count:
            for i in range(horizontal_fridge_count):
                layout_objects.append({
                    'id': f'HORIZONTAL_FRIDGE_{i+1}',
                    'label': f'YATAY DOLAP {i+1}',
                    'type': 'horizontal_fridge',
                    'zone': 'CHILLED',
                    'x': 36 + (i % 4) * 12, 'y': 72 + (i // 4) * 7, 'w': 8, 'd': 3.5, 'h': 1.2,
                    'rotation': 0,
                    'modules': 1,
                    'shelves': 3,
                    'temperature_c': 4,
                    'left_modules': [{
                        'module_id': f'HF-{i+1}-M1',
                        'module_position': 1,
                        'fixture_type': 'horizontal_fridge',
                        'fixture_family': 'horizontal_cooler',
                        'dimensions': {'width': 150, 'depth': 70, 'height': 110},
                        'shelves': [
                            {'shelf_no': s + 1, 'shelf_label': f'HF-{i+1}-R{s+1}', 'height_from_ground_cm': 10 + (s * 28), 'dimensions': {'width_cm': 150, 'depth_cm': 70, 'height_cm': 25}, 'allowed_storage_type': ['CHILLED'], 'max_weight_kg': 50}
                            for s in range(3)
                        ],
                        'total_shelves': 3,
                    }],
                    'right_modules': []
                })

        # 5d. Martek +4 dikey dolaplar - varsa ayrı fixture olarak korunur
        if martek_plus4_count:
            for i in range(martek_plus4_count):
                layout_objects.append({
                    'id': f'MARTEK_PLUS4_{i+1}',
                    'label': f'MARTEK +4 DOLAP {i+1}',
                    'type': 'martek_plus4',
                    'zone': 'CHILLED',
                    'x': 70 + (i % 5) * 7, 'y': 86 + (i // 5) * 6, 'w': 5, 'd': 3, 'h': 2.1,
                    'rotation': 0,
                    'modules': 1,
                    'shelves': 5,
                    'temperature_c': 4,
                    'left_modules': [{
                        'module_id': f'MARTEK-{i+1}-M1',
                        'module_position': 1,
                        'fixture_type': 'martek_plus4',
                        'fixture_family': 'cooler',
                        'dimensions': {'width': 100, 'depth': 60, 'height': 210},
                        'shelves': [
                            {'shelf_no': s + 1, 'shelf_label': f'MARTEK-{i+1}-R{s+1}', 'height_from_ground_cm': 20 + (s * 35), 'dimensions': {'width_cm': 100, 'depth_cm': 60, 'height_cm': 30}, 'allowed_storage_type': ['CHILLED'], 'max_weight_kg': 45}
                            for s in range(5)
                        ],
                        'total_shelves': 5,
                    }],
                    'right_modules': []
                })

        # 6. Dispatch area
        layout_objects.append({
            'id': 'DISPATCH',
            'label': 'SEVKİYAT',
            'type': 'dispatch',
            'zone': 'DISPATCH',
            'x': 108, 'y': 42, 'w': 19, 'd': 13, 'h': 2.8,
            'rotation': 0,
            'modules': 0,
            'shelves': 0
        })
        
        # Physics-first fixture instances. These are the canonical Store DNA
        # instances for equipment that does not behave like a standard aisle.
        fixture_instances = []
        for i in range(max(0, int(wizard_input.get('martek_frozen_count', 0) or 0))):
            fixture_instances.append({'id': f'MARTEK_FROZEN_{i+1}', 'fixture_type': 'martek_frozen_minus18', 'count': 1, 'width_cm': 120, 'depth_cm': 70, 'height_cm': 200, 'shelf_count': 4, 'zone': 'FROZEN'})
        for i in range(max(0, int(wizard_input.get('produce_chilled_count', 0) or 0))):
            fixture_instances.append({'id': f'PRODUCE_CHILLED_{i+1}', 'fixture_type': 'produce_chilled_shelf', 'count': 1, 'width_cm': 120, 'depth_cm': 60, 'height_cm': 180, 'shelf_count': 4, 'zone': 'FRESH'})
        for i in range(max(0, int(wizard_input.get('new_gen_steel_rack_count', 0) or 0))):
            fixture_instances.append({'id': f'NEW_GEN_STEEL_{i+1}', 'fixture_type': 'new_gen_steel_rack', 'count': 1, 'width_cm': 100, 'depth_cm': 60, 'height_cm': 250, 'shelf_count': 6, 'zone': 'AMBIENT'})

        # Calculate fixture summary
        fixture_summary = self._calculate_fixture_summary(layout_objects)
        fixture_summary['fixture_instances'] = len(fixture_instances)
        
        return {
            'store_code': store_code,
            'store_name': store_name,
            'created_by': 'easy_wizard',
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'wizard_type': 'easy',
            'layout_objects': layout_objects,
            'fixture_instances': fixture_instances,
            'fixture_summary': fixture_summary,
            'metadata': {
                'warehouse_size': wizard_input.get('warehouse_size', 'medium'),
                'total_aisles': num_aisles,
                'has_chilled': has_chilled,
                'has_frozen': has_frozen,
                'has_algida': has_algida,
                'algida_count': algida_count,
                'horizontal_fridge_count': horizontal_fridge_count,
                'martek_plus4_count': martek_plus4_count,
                'left_modules_per_aisle': left_modules_per_aisle,
                'right_modules_per_aisle': right_modules_per_aisle,
                'left_fixture_type': left_fixture_type,
                'right_fixture_type': right_fixture_type
            }
        }
    
    def build_from_template(self, template_id: str, store_code: str, store_name: str, overrides: Dict = None) -> Dict[str, Any]:
        """
        Build Store DNA from template
        
        Templates:
            - ecommerce_warehouse
            - retail_warehouse
            - cold_chain_warehouse
        """
        templates = self._get_templates()
        
        if template_id not in templates:
            raise ValueError(f"Unknown template: {template_id}")
        
        template = templates[template_id]
        
        dna = {
            'store_code': store_code,
            'store_name': store_name,
            'created_by': 'template_wizard',
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'wizard_type': 'template',
            'template_id': template_id,
            'layout_objects': template['layout_objects'],
            'fixture_summary': self._calculate_fixture_summary(template['layout_objects']),
            'metadata': template.get('metadata', {})
        }
        
        # Apply overrides
        if overrides:
            if 'layout_objects' in overrides:
                dna['layout_objects'] = overrides['layout_objects']
                dna['fixture_summary'] = self._calculate_fixture_summary(dna['layout_objects'])
        
        return dna
    
    def _calculate_fixture_summary(self, layout_objects: List[Dict]) -> Dict[str, Any]:
        """Calculate fixture capacity summary"""
        summary = {
            'total_objects': len(layout_objects),
            'by_type': {},
            'by_zone': {},
            'planogram_eligible': [],
            'total_shelves': 0,
            'total_modules': 0,
            'capacity_by_storage': {
                'AMBIENT': 0,
                'CHILLED': 0,
                'FROZEN': 0
            }
        }
        
        for obj in layout_objects:
            obj_type = obj.get('type', 'unknown')
            zone = obj.get('zone', 'UNKNOWN')
            
            # Count by type
            summary['by_type'][obj_type] = summary['by_type'].get(obj_type, 0) + 1
            
            # Count by zone
            summary['by_zone'][zone] = summary['by_zone'].get(zone, 0) + 1
            
            # Planogram eligible
            fixture_info = self.FIXTURE_TYPES.get(obj_type, {})
            if fixture_info.get('planogram_eligible', False):
                summary['planogram_eligible'].append(obj['id'])
                nested_modules = obj.get('left_modules', []) + obj.get('right_modules', [])
                nested_shelves = sum(len(m.get('shelves', [])) for m in nested_modules)
                summary['total_shelves'] += nested_shelves or obj.get('shelves', 0)
                summary['total_modules'] += len(nested_modules) or obj.get('modules', 0)
                
                # Capacity by storage type
                if zone == 'AMBIENT':
                    summary['capacity_by_storage']['AMBIENT'] += obj.get('shelves', 0)
                elif zone == 'CHILLED':
                    summary['capacity_by_storage']['CHILLED'] += obj.get('shelves', 0)
                elif zone == 'FROZEN':
                    summary['capacity_by_storage']['FROZEN'] += obj.get('shelves', 0)
        
        return summary
    
    def _get_templates(self) -> Dict[str, Dict]:
        """Warehouse templates"""
        return {
            'ecommerce_warehouse': {
                'name': 'E-Ticaret Depo',
                'description': '9 koridor, büyük dispatch zone',
                'metadata': {'type': 'ecommerce', 'focus': 'high_throughput'},
                'layout_objects': [
                    {'id': 'RECEIVING', 'label': 'MAL KABUL', 'type': 'receiving', 'zone': 'INBOUND', 'x': 6, 'y': 5, 'w': 25, 'd': 15, 'h': 3.5, 'rotation': 0, 'modules': 0, 'shelves': 0},
                    {'id': 'A', 'label': 'A', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 12, 'y': 24, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'B', 'label': 'B', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 50, 'y': 24, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'C', 'label': 'C', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 88, 'y': 24, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'D', 'label': 'D', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 12, 'y': 47, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'E', 'label': 'E', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 50, 'y': 47, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'F', 'label': 'F', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 88, 'y': 47, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'G', 'label': 'G', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 12, 'y': 70, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'H', 'label': 'H', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 50, 'y': 70, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'I', 'label': 'I', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 88, 'y': 70, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'DISPATCH', 'label': 'SEVKİYAT', 'type': 'dispatch', 'zone': 'DISPATCH', 'x': 108, 'y': 35, 'w': 25, 'd': 20, 'h': 2.8, 'rotation': 0, 'modules': 0, 'shelves': 0},
                ]
            },
            
            'retail_warehouse': {
                'name': 'Perakende Depo',
                'description': '12 koridor, produce + chilled ağırlıklı',
                'metadata': {'type': 'retail', 'focus': 'fresh_products'},
                'layout_objects': [
                    {'id': 'RECEIVING', 'label': 'MAL KABUL', 'type': 'receiving', 'zone': 'INBOUND', 'x': 6, 'y': 5, 'w': 20, 'd': 12, 'h': 3.5, 'rotation': 0, 'modules': 0, 'shelves': 0},
                    {'id': 'A', 'label': 'A', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 12, 'y': 24, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'B', 'label': 'B', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 50, 'y': 24, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'C', 'label': 'C', 'type': 'corridor', 'zone': 'AMBIENT', 'x': 88, 'y': 24, 'w': 30, 'd': 8, 'h': 2.5, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'PRODUCE', 'label': 'MEYVE SEBZE', 'type': 'produce_shelf', 'zone': 'AMBIENT', 'x': 12, 'y': 50, 'w': 40, 'd': 6, 'h': 1.8, 'rotation': 0, 'modules': 10, 'shelves': 40},
                    {'id': 'CHILLED_ROOM', 'label': '+4 SOĞUK ODA', 'type': 'chilled_room', 'zone': 'CHILLED', 'x': 60, 'y': 50, 'w': 30, 'd': 20, 'h': 3.2, 'rotation': 0, 'modules': 6, 'shelves': 30},
                    {'id': 'FROZEN_ROOM', 'label': '-18 DONUK ODA', 'type': 'frozen_room', 'zone': 'FROZEN', 'x': 95, 'y': 50, 'w': 25, 'd': 18, 'h': 3.2, 'rotation': 0, 'modules': 4, 'shelves': 20},
                    {'id': 'DISPATCH', 'label': 'SEVKİYAT', 'type': 'dispatch', 'zone': 'DISPATCH', 'x': 108, 'y': 75, 'w': 20, 'd': 15, 'h': 2.8, 'rotation': 0, 'modules': 0, 'shelves': 0},
                ]
            },
            
            'cold_chain_warehouse': {
                'name': 'Soğuk Zincir Depo',
                'description': 'Chilled/Frozen ağırlıklı',
                'metadata': {'type': 'cold_chain', 'focus': 'temperature_control'},
                'layout_objects': [
                    {'id': 'RECEIVING_COLD', 'label': 'SOĞUK MAL KABUL', 'type': 'receiving', 'zone': 'INBOUND', 'x': 6, 'y': 5, 'w': 20, 'd': 12, 'h': 3.5, 'rotation': 0, 'modules': 0, 'shelves': 0},
                    {'id': 'CHILLED_ROOM_1', 'label': '+4 ODA 1', 'type': 'chilled_room', 'zone': 'CHILLED', 'x': 12, 'y': 24, 'w': 35, 'd': 25, 'h': 3.2, 'rotation': 0, 'modules': 8, 'shelves': 48},
                    {'id': 'CHILLED_ROOM_2', 'label': '+4 ODA 2', 'type': 'chilled_room', 'zone': 'CHILLED', 'x': 55, 'y': 24, 'w': 35, 'd': 25, 'h': 3.2, 'rotation': 0, 'modules': 8, 'shelves': 48},
                    {'id': 'FROZEN_ROOM_1', 'label': '-18 ODA 1', 'type': 'frozen_room', 'zone': 'FROZEN', 'x': 12, 'y': 55, 'w': 35, 'd': 25, 'h': 3.2, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'FROZEN_ROOM_2', 'label': '-18 ODA 2', 'type': 'frozen_room', 'zone': 'FROZEN', 'x': 55, 'y': 55, 'w': 35, 'd': 25, 'h': 3.2, 'rotation': 0, 'modules': 6, 'shelves': 36},
                    {'id': 'ALGIDA_ZONE', 'label': 'DONDURMA BÖLGESI', 'type': 'ice_cream_chest_freezer_large', 'zone': 'FROZEN', 'x': 95, 'y': 55, 'w': 25, 'd': 12, 'h': 2.1, 'rotation': 0, 'modules': 4, 'shelves': 16},
                    {'id': 'DISPATCH', 'label': 'SEVKİYAT', 'type': 'dispatch', 'zone': 'DISPATCH', 'x': 95, 'y': 24, 'w': 25, 'd': 20, 'h': 2.8, 'rotation': 0, 'modules': 0, 'shelves': 0},
                ]
            }
        }
    
    def get_fixture_pools_from_dna(self, dna: Dict[str, Any]) -> Dict[str, List[Dict]]:
        """Build physics-first fixture pools from Store DNA.

        This replaces the old object-level pool extraction. It returns shelf-level
        slots keyed by storage class and never truncates fixture/module counts.
        """
        try:
            from services.fixture_pool_builder import build_fixture_pools
        except Exception:
            from .fixture_pool_builder import build_fixture_pools
        return build_fixture_pools(dna)

    def get_fixture_pool_summary_from_dna(self, dna: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from services.fixture_pool_builder import build_fixture_pools, summarize_pools
        except Exception:
            from .fixture_pool_builder import build_fixture_pools, summarize_pools
        return summarize_pools(build_fixture_pools(dna))


# Singleton instance
store_dna_service = StoreDNAService()
