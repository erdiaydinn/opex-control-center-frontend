"""
PLONAGRAM OS - Catalog Service
Catalog import, column normalization, data enrichment
"""

from typing import Dict, List, Any, Optional
import pandas as pd
from io import BytesIO


class CatalogService:
    """Catalog data management"""
    
    # Column alias mapping
    COLUMN_ALIASES = {
        'sku': ['sku', 'SKU', 'product_code', 'item_code', 'stok_kodu', 'Product Code'],
        'barcode': ['barcode', 'Barcode', 'barkod', 'EAN', 'GTIN', 'product_barcodes', 'Barcodes'],
        'product_name': ['product_name', 'name', 'urun_adi', 'Product Name', 'product_name_local'],
        'brand': ['brand', 'Brand', 'marka', 'brand_name', 'Brand Name'],
        'category_l1': ['category', 'Category L1', 'kategori', 'main_category', 'frontend_category_local', 'Category'],
        'category_l2': ['subcategory', 'Category L2', 'alt_kategori', 'sub_category', 'frontend_subcategory_local', 'Subcategory'],
        'storage_type': ['storage_type', 'storage', 'depolama_tipi', 'Storage Type', 'Storage'],
        'width_cm': ['width_cm', 'width', 'genislik', 'Width (cm)', 'Width', 'product_width_cm', 'product_width_in_cm'],
        'height_cm': ['height_cm', 'height', 'yukseklik', 'Height (cm)', 'Height', 'product_height_cm', 'product_height_in_cm'],
        'depth_cm': ['depth_cm', 'depth', 'derinlik', 'Depth (cm)', 'Depth', 'product_depth_cm', 'product_length_in_cm', 'product_depth_in_cm'],
        'weight_kg': ['weight_kg', 'weight', 'agirlik', 'Weight (kg)', 'Weight', 'product_weight_kg', 'product_weight_value'],
        'image_url': ['image_url', 'Product Image URL', 'gorsel', 'photo_url', 'image', 'catalog_image_url', 'pim_image_url'],
        'case_pack': ['case_pack', 'case_pack_qty', 'koli_miktari', 'Case Pack', 'Pack Size'],
    }
    
    # Storage type inference rules
    STORAGE_INFERENCE_RULES = {
        'CHILLED': {
            'keywords': ['süt', 'yoğurt', 'peynir', 'tereyağ', 'milk', 'yogurt', 'cheese', 'butter', 'fresh', 'taze'],
            'categories': ['Süt Ürünleri', 'Dairy', 'Şarküteri', 'Deli']
        },
        'FROZEN': {
            'keywords': ['dondurma', 'donuk', 'frozen', 'ice cream', '-18'],
            'categories': ['Dondurma', 'Donuk', 'Frozen']
        },
        'AMBIENT': {
            'default': True  # Fallback
        }
    }
    
    def import_from_file(self, file_content: bytes, filename: str, store_code: str) -> Dict[str, Any]:
        """
        Import catalog from CSV or XLSX file
        
        Returns:
            {
                'products': [...],
                'total_count': int,
                'columns_mapped': {...},
                'errors': [...]
            }
        """
        # Read file
        if filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(file_content))
        elif filename.endswith('.xlsx'):
            df = pd.read_excel(BytesIO(file_content))
        else:
            raise ValueError(f"Unsupported file format: {filename}")
        
        # Normalize columns
        df, column_mapping = self._normalize_columns(df)
        
        # Convert to dict
        products = []
        errors = []
        
        for idx, row in df.iterrows():
            try:
                product = self._row_to_product(row, store_code)
                products.append(product)
            except Exception as e:
                errors.append({
                    'row': idx + 2,  # Excel row number (1-indexed + header)
                    'error': str(e),
                    'data': row.to_dict()
                })
        
        return {
            'products': products,
            'total_count': len(products),
            'columns_mapped': column_mapping,
            'errors': errors,
            'summary': {
                'total_rows': len(df),
                'successful': len(products),
                'failed': len(errors),
                'has_storage_type': sum(1 for p in products if p.get('storage_type')),
                'has_dimensions': sum(1 for p in products if p.get('width_cm') and p.get('height_cm')),
                'has_image': sum(1 for p in products if p.get('image_url'))
            }
        }
    
    def _normalize_columns(self, df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, str]]:
        """
        Normalize column names using alias mapping
        
        Returns: (normalized_df, mapping_dict)
        """
        mapping = {}
        rename_dict = {}
        
        for standard_name, aliases in self.COLUMN_ALIASES.items():
            for col in df.columns:
                if col in aliases:
                    rename_dict[col] = standard_name
                    mapping[standard_name] = col
                    break
        
        df_normalized = df.rename(columns=rename_dict)
        
        return df_normalized, mapping
    
    def _row_to_product(self, row: pd.Series, store_code: str) -> Dict[str, Any]:
        """Convert DataFrame row to product dict"""
        product = {
            'store_code': store_code,
            'sku': self._clean_text(row.get('sku')),
            'barcode': self._clean_text(row.get('barcode')),
            'product_name': self._clean_text(row.get('product_name')),
            'brand': self._clean_text(row.get('brand')),
            'category_l1': self._clean_text(row.get('category_l1')),
            'category_l2': self._clean_text(row.get('category_l2')),
            'storage_type': self._clean_text(row.get('storage_type')),
            'width_cm': self._parse_float(row.get('width_cm')),
            'height_cm': self._parse_float(row.get('height_cm')),
            'depth_cm': self._parse_float(row.get('depth_cm')),
            'weight_kg': self._parse_float(row.get('weight_kg')),
            'image_url': self._clean_text(row.get('image_url')),
            'case_pack': self._parse_int(row.get('case_pack'), default=1),
        }
        
        # Storage type inference if missing
        if not product['storage_type']:
            product['storage_type'] = self._infer_storage_type(product)
        
        # Normalize storage type
        product['storage_type'] = self._normalize_storage_type(product['storage_type'])
        
        return product
    
    def _clean_text(self, value: Any) -> str:
        """Clean text field"""
        if pd.isna(value) or value is None:
            return ''
        
        text = str(value).strip()
        
        # Remove common Excel artifacts
        if text.lower() in ['nan', 'none', 'null', '#n/a']:
            return ''
        
        return text
    
    def _parse_float(self, value: Any) -> Optional[float]:
        """Parse float field"""
        if pd.isna(value) or value is None or value == '':
            return None
        
        try:
            # Handle comma as decimal separator
            if isinstance(value, str):
                value = value.replace(',', '.')
            return float(value)
        except:
            return None
    
    def _parse_int(self, value: Any, default: int = 0) -> int:
        """Parse int field"""
        if pd.isna(value) or value is None or value == '':
            return default
        
        try:
            return int(float(value))
        except:
            return default
    
    def _infer_storage_type(self, product: Dict[str, Any]) -> str:
        """
        Infer storage type from product name, brand, category
        Rules-based inference
        """
        # Combine searchable text
        search_text = ' '.join([
            product.get('product_name', ''),
            product.get('brand', ''),
            product.get('category_l1', ''),
            product.get('category_l2', '')
        ]).lower()
        
        # Check CHILLED keywords
        for keyword in self.STORAGE_INFERENCE_RULES['CHILLED']['keywords']:
            if keyword in search_text:
                return 'CHILLED'
        
        # Check CHILLED categories
        for category in self.STORAGE_INFERENCE_RULES['CHILLED']['categories']:
            if category.lower() in search_text:
                return 'CHILLED'
        
        # Check FROZEN keywords
        for keyword in self.STORAGE_INFERENCE_RULES['FROZEN']['keywords']:
            if keyword in search_text:
                return 'FROZEN'
        
        # Check FROZEN categories
        for category in self.STORAGE_INFERENCE_RULES['FROZEN']['categories']:
            if category.lower() in search_text:
                return 'FROZEN'
        
        if any(x in search_text for x in ['algida', 'magnum', 'cornetto']):
            return 'FROZEN'
        if any(x in search_text for x in ['maydanoz', 'marul', 'roka', 'dereotu', 'nane', 'parsley', 'lettuce']):
            return 'CHILLED'
        if any(x in search_text for x in ['patates', 'soğan', 'sogan', 'mandalina', 'muz', 'banana', 'potato', 'onion']):
            return 'AMBIENT'
        # Default: AMBIENT
        return 'AMBIENT'
    
    def _normalize_storage_type(self, storage: str) -> str:
        """Normalize storage type to standard values"""
        if not storage:
            return 'AMBIENT'
        
        storage_upper = storage.strip().upper()
        
        # Map variations
        if storage_upper in ['CHILLED', 'COLD', 'SOĞUK', '+4', 'REFRIGERATED']:
            return 'CHILLED'
        elif storage_upper in ['FROZEN', 'DONUK', '-18', 'FREEZER']:
            return 'FROZEN'
        else:
            return 'AMBIENT'
    
    def validate_catalog_quality(self, products: List[Dict]) -> Dict[str, Any]:
        """
        Validate catalog data quality
        Returns quality report
        """
        total = len(products)
        
        report = {
            'total_products': total,
            'missing_sku': sum(1 for p in products if not p.get('sku')),
            'missing_name': sum(1 for p in products if not p.get('product_name')),
            'missing_brand': sum(1 for p in products if not p.get('brand')),
            'missing_category': sum(1 for p in products if not p.get('category_l2')),
            'missing_storage_type': sum(1 for p in products if not p.get('storage_type')),
            'missing_width': sum(1 for p in products if not p.get('width_cm')),
            'missing_height': sum(1 for p in products if not p.get('height_cm')),
            'missing_depth': sum(1 for p in products if not p.get('depth_cm')),
            'missing_image': sum(1 for p in products if not p.get('image_url')),
            'complete_products': 0
        }
        
        # Count complete products (have all essential fields)
        report['complete_products'] = sum(
            1 for p in products
            if all([
                p.get('sku'),
                p.get('product_name'),
                p.get('brand'),
                p.get('storage_type'),
                p.get('width_cm'),
                p.get('height_cm'),
                p.get('depth_cm')
            ])
        )
        
        # Calculate percentages
        report['quality_score'] = round(report['complete_products'] / max(total, 1) * 100, 1)
        
        # Issues
        report['issues'] = []
        if report['missing_sku'] > 0:
            report['issues'].append(f"{report['missing_sku']} products missing SKU")
        if report['missing_storage_type'] > 0:
            report['issues'].append(f"{report['missing_storage_type']} products missing storage_type")
        if report['missing_width'] > total * 0.1:
            report['issues'].append(f"{report['missing_width']} products missing dimensions")
        if report['missing_image'] > total * 0.5:
            report['issues'].append(f"{report['missing_image']} products missing image URL")
        
        return report


# Singleton
catalog_service = CatalogService()
