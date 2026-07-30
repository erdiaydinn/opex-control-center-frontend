"""
PLONAGRAM OS - Merge Service
ABC Report + Catalog merge with intelligent entity resolution
"""

from typing import Dict, List, Tuple, Any, Optional
import re
from difflib import SequenceMatcher


class MergeService:
    """ABC + Catalog intelligent merge"""
    
    def __init__(self):
        self.match_stats = {
            'sku_match': 0,
            'barcode_match': 0,
            'product_key_match': 0,
            'fuzzy_match': 0,
            'unmatched': 0
        }
    
    def merge_abc_catalog(self, abc_items: List[Dict], catalog_items: List[Dict]) -> Dict[str, Any]:
        """
        Merge ABC report with Catalog
        
        Returns:
            {
                'merged_products': [...],
                'unmatched_abc': [...],
                'unmatched_catalog': [...],
                'match_stats': {...}
            }
        """
        # Reset stats
        self.match_stats = {k: 0 for k in self.match_stats}
        
        # 1. Index catalog by all possible keys
        catalog_by_sku = {}
        catalog_by_barcode = {}
        catalog_by_product_key = {}
        
        for catalog in catalog_items:
            # SKU index
            sku_norm = self._normalize_sku(catalog.get('sku', ''))
            if sku_norm:
                catalog_by_sku[sku_norm] = catalog
            
            # Barcode index (can be multiple barcodes)
            barcodes = self._extract_barcodes(catalog.get('barcode', ''))
            for bc in barcodes:
                catalog_by_barcode[bc] = catalog
            
            # Product key index
            pkey = self._build_product_key(catalog)
            if pkey:
                catalog_by_product_key[pkey] = catalog
        
        merged = []
        unmatched_abc = []
        matched_catalog_skus = set()
        
        # 2. Match each ABC item
        for abc in abc_items:
            catalog_match = None
            match_method = None
            match_confidence = 0.0
            
            # Strategy 1: Direct SKU match
            sku_norm = self._normalize_sku(abc.get('sku', ''))
            if sku_norm and sku_norm in catalog_by_sku:
                catalog_match = catalog_by_sku[sku_norm]
                match_method = 'sku_match'
                match_confidence = 1.0
                self.match_stats['sku_match'] += 1
            
            # Strategy 2: Barcode match (BARCODE ALWAYS WINS)
            elif abc.get('barcode'):
                abc_barcodes = self._extract_barcodes(abc.get('barcode', ''))
                for bc in abc_barcodes:
                    if bc in catalog_by_barcode:
                        catalog_match = catalog_by_barcode[bc]
                        match_method = 'barcode_match'
                        match_confidence = 0.98  # SPEC: 0.98 for barcode
                        self.match_stats['barcode_match'] += 1
                        break
            
            # Strategy 3: Product key match
            if not catalog_match:
                abc_key = self._build_product_key(abc)
                if abc_key and abc_key in catalog_by_product_key:
                    catalog_match = catalog_by_product_key[abc_key]
                    match_method = 'product_key_match'
                    match_confidence = 0.85
                    self.match_stats['product_key_match'] += 1
            
            # Strategy 4: Fuzzy name + brand match (NO AUTO-MERGE)
            if not catalog_match:
                fuzzy_result = self._fuzzy_match_catalog(abc, catalog_items)
                if fuzzy_result:
                    catalog_match, similarity = fuzzy_result
                    match_method = 'fuzzy_match'
                    match_confidence = similarity
                    
                    # CRITICAL: Fuzzy match does NOT auto-merge
                    # Only suggest if >= 0.90
                    if similarity >= 0.90:
                        # High confidence suggestion - mark for user review
                        self.match_stats['fuzzy_match'] += 1
                    elif similarity >= 0.75:
                        # Medium confidence - flag for review
                        match_method = 'fuzzy_review'
                        self.match_stats['fuzzy_match'] += 1
                    else:
                        # Low confidence - unmatched
                        catalog_match = None
                        match_method = None
                        match_confidence = 0.0
            
            # Merge or mark as unmatched
            if catalog_match and match_method in ['sku_match', 'barcode_match', 'product_key_match']:
                # Auto-merge only for high-confidence matches
                merged_product = self._merge_abc_and_catalog(abc, catalog_match, match_method, match_confidence)
                merged.append(merged_product)
                
                # Track matched catalog items
                matched_sku = self._normalize_sku(catalog_match.get('sku', ''))
                if matched_sku:
                    matched_catalog_skus.add(matched_sku)
                    
            elif catalog_match and match_method in ['fuzzy_match', 'fuzzy_review']:
                # Fuzzy matches go to unmatched with suggestions
                self.match_stats['unmatched'] += 1
                unmatched_abc.append({
                    **abc,
                    '_reason': 'fuzzy_match_requires_review',
                    '_match_confidence': match_confidence,
                    '_suggested_catalog_sku': catalog_match.get('sku'),
                    '_suggested_catalog_name': catalog_match.get('product_name'),
                    '_suggestions': [catalog_match]  # Single best suggestion
                })
            else:
                # No match found
                self.match_stats['unmatched'] += 1
                unmatched_abc.append({
                    **abc,
                    '_reason': 'catalog_match_failed',
                    '_suggestions': self._get_match_suggestions(abc, catalog_items)
                })
        
        # 3. Find unmatched catalog items
        unmatched_catalog = []
        for catalog in catalog_items:
            sku_norm = self._normalize_sku(catalog.get('sku', ''))
            if sku_norm and sku_norm not in matched_catalog_skus:
                unmatched_catalog.append({
                    **catalog,
                    '_reason': 'not_in_abc_report',
                    '_note': 'Catalog\'da var ama ABC raporunda yok - satış verisi olmayabilir'
                })
        
        return {
            'merged_products': merged,
            'unmatched_abc': unmatched_abc,
            'unmatched_catalog': unmatched_catalog,
            'match_stats': self.match_stats,
            'summary': {
                'total_abc_items': len(abc_items),
                'total_catalog_items': len(catalog_items),
                'total_merged': len(merged),
                'unmatched_abc_count': len(unmatched_abc),
                'unmatched_catalog_count': len(unmatched_catalog),
                'match_rate': round(len(merged) / max(len(abc_items), 1) * 100, 2)
            }
        }
    
    def _normalize_sku(self, sku: Any) -> str:
        """Normalize SKU for matching"""
        if not sku:
            return ''
        
        # Convert to string, strip, uppercase, remove special chars
        sku_str = str(sku).strip().upper()
        sku_str = re.sub(r'[^A-Z0-9]', '', sku_str)
        return sku_str
    
    def _extract_barcodes(self, barcode_field: Any) -> List[str]:
        """Extract and normalize barcodes (can be multiple separated by |, ;, ,)"""
        if not barcode_field:
            return []
        
        barcode_str = str(barcode_field).strip()
        
        # Split by common separators
        barcodes = re.split(r'[|;,\s]+', barcode_str)
        
        # Normalize each barcode
        normalized = []
        for bc in barcodes:
            bc_clean = re.sub(r'[^0-9]', '', bc.strip())
            if bc_clean and len(bc_clean) >= 8:  # Valid barcode min length
                normalized.append(bc_clean)
        
        return normalized
    
    def _normalize_text(self, text: Any) -> str:
        """Normalize text for comparison"""
        if not text:
            return ''
        
        text_str = str(text).strip().lower()
        
        # Turkish character normalization
        replacements = {
            'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
            'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
        }
        for tr_char, en_char in replacements.items():
            text_str = text_str.replace(tr_char, en_char)
        
        # Remove extra spaces
        text_str = re.sub(r'\s+', ' ', text_str)
        
        return text_str
    
    def _build_product_key(self, product: Dict) -> str:
        """
        Build composite product key for matching
        Format: brand|name_normalized|weight|unit|category
        """
        brand = self._normalize_text(product.get('brand', ''))
        name = self._normalize_text(product.get('product_name', '') or product.get('name', ''))
        
        # Extract weight info
        weight_value = self._normalize_text(product.get('product_contents_value', '') or 
                                           product.get('weight_value', '') or
                                           product.get('weight_kg', ''))
        weight_unit = self._normalize_text(product.get('product_contents_unit', '') or
                                          product.get('weight_unit', ''))
        
        category = self._normalize_text(product.get('category_l2', '') or 
                                       product.get('subcategory', '') or
                                       product.get('category', ''))
        
        if not brand or not name:
            return ''
        
        key = f"{brand}|{name}|{weight_value}|{weight_unit}|{category}"
        return key
    
    def _fuzzy_match_catalog(self, abc: Dict, catalog_items: List[Dict]) -> Optional[Tuple[Dict, float]]:
        """
        Fuzzy match ABC item to catalog based on name + brand similarity
        Returns: (catalog_match, similarity_score) or None
        """
        abc_name = self._normalize_text(abc.get('product_name', '') or abc.get('name', ''))
        abc_brand = self._normalize_text(abc.get('brand', ''))
        
        if not abc_name:
            return None
        
        best_match = None
        best_score = 0.0
        
        for catalog in catalog_items:
            catalog_name = self._normalize_text(catalog.get('product_name', '') or catalog.get('name', ''))
            catalog_brand = self._normalize_text(catalog.get('brand', ''))
            
            if not catalog_name:
                continue
            
            # Name similarity
            name_similarity = SequenceMatcher(None, abc_name, catalog_name).ratio()
            
            # Brand similarity
            brand_similarity = 1.0 if abc_brand == catalog_brand else 0.0
            
            # Combined score (brand is more important)
            combined_score = (name_similarity * 0.6) + (brand_similarity * 0.4)
            
            if combined_score > best_score:
                best_score = combined_score
                best_match = catalog
        
        if best_score > 0.75:  # Threshold for fuzzy match
            return (best_match, best_score)
        
        return None
    
    def _get_match_suggestions(self, abc: Dict, catalog_items: List[Dict], limit: int = 3) -> List[Dict]:
        """Get top N similar catalog items as suggestions"""
        abc_name = self._normalize_text(abc.get('product_name', '') or abc.get('name', ''))
        
        if not abc_name:
            return []
        
        scored = []
        for catalog in catalog_items:
            catalog_name = self._normalize_text(catalog.get('product_name', '') or catalog.get('name', ''))
            if catalog_name:
                similarity = SequenceMatcher(None, abc_name, catalog_name).ratio()
                scored.append((catalog, similarity))
        
        # Sort by similarity
        scored.sort(key=lambda x: -x[1])
        
        # Return top N
        suggestions = []
        for catalog, score in scored[:limit]:
            if score > 0.5:  # Minimum threshold
                suggestions.append({
                    'sku': catalog.get('sku'),
                    'name': catalog.get('product_name') or catalog.get('name'),
                    'brand': catalog.get('brand'),
                    'similarity': round(score, 2)
                })
        
        return suggestions
    
    def _merge_abc_and_catalog(self, abc: Dict, catalog: Dict, match_method: str, match_confidence: float) -> Dict:
        """
        Merge ABC sales data + Catalog master data
        Priority: Catalog data is base, ABC overrides sales metrics
        """
        merged = {
            # Base: Catalog master data
            **catalog,
            
            # Override: ABC sales data
            'sku': abc.get('sku') or catalog.get('sku'),
            'sales_7d': self._parse_number(abc.get('sales_qty_7d', 0)),
            'sales_qty_7d': self._parse_number(abc.get('sales_qty_7d', 0)),
            'percent_orders': self._parse_number(abc.get('percent_orders', 0)),
            'percent_stops': self._parse_number(abc.get('percent_stops', 0)),
            'abc_class': abc.get('abc_class', 'C'),
            'rank': self._parse_number(abc.get('rank', 999), as_int=True),
            
            # Metadata
            '_match_method': match_method,
            '_match_confidence': match_confidence,
            '_abc_source': True,
            '_catalog_source': True
        }
        
        # If product_name differs, keep both
        if abc.get('product_name') and abc.get('product_name') != catalog.get('product_name'):
            merged['_abc_product_name'] = abc.get('product_name')
        
        return merged
    
    def _parse_number(self, value: Any, default: float = 0.0, as_int: bool = False) -> float:
        """Parse number from various formats"""
        if value is None or value == '':
            return int(default) if as_int else default
        
        try:
            # Remove % sign, commas
            if isinstance(value, str):
                value = value.replace('%', '').replace(',', '.').strip()
            
            num = float(value)
            return int(num) if as_int else num
        except:
            return int(default) if as_int else default


# Singleton
merge_service = MergeService()
