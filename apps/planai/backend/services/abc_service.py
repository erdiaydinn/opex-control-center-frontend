"""
PLONAGRAM OS - ABC Service
ABC Report import and normalization
"""

from typing import Dict, List, Any
import pandas as pd
from io import BytesIO


class ABCService:
    """ABC Report management"""
    
    # Column alias mapping for ABC reports
    COLUMN_ALIASES = {
        'sku': ['sku', 'SKU', 'product_code', 'item_code', 'stok_kodu'],
        'product_name': ['product_name', 'name', 'urun_adi', 'Product Name', 'product'],
        'brand': ['brand', 'Brand', 'marka'],
        'barcode': ['barcode', 'Barcode', 'barkod'],
        'sales_qty_7d': ['sales_7d', 'weekly_sales', 'haftalik_satis', 'Sales (7d)', 'Quantity'],
        'percent_orders': ['percent_orders', '% Orders', 'siparis_yuzdesi', '% of Orders'],
        'percent_stops': ['percent_stops', '% Stops', 'duraklama_yuzdesi', '% of Stops'],
        'abc_class': ['abc_class', 'ABC Class', 'ABC', 'class', 'Sınıf'],
        'rank': ['rank', 'Rank', 'ranking', 'sira', 'Sıra'],
    }
    
    def import_from_file(self, file_content: bytes, filename: str, store_code: str) -> Dict[str, Any]:
        """
        Import ABC report from CSV or XLSX
        
        Returns:
            {
                'items': [...],
                'total_count': int,
                'columns_mapped': {...},
                'errors': [...],
                'summary': {...}
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
        
        # Convert to items
        items = []
        errors = []
        
        for idx, row in df.iterrows():
            try:
                item = self._row_to_abc_item(row, store_code)
                items.append(item)
            except Exception as e:
                errors.append({
                    'row': idx + 2,
                    'error': str(e),
                    'data': row.to_dict()
                })
        
        # Calculate ABC classes if missing
        if not any(item.get('abc_class') for item in items):
            items = self._calculate_abc_classes(items)
        
        return {
            'items': items,
            'total_count': len(items),
            'columns_mapped': column_mapping,
            'errors': errors,
            'summary': self._calculate_summary(items)
        }
    
    def _normalize_columns(self, df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, str]]:
        """Normalize column names"""
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
    
    def _row_to_abc_item(self, row: pd.Series, store_code: str) -> Dict[str, Any]:
        """Convert row to ABC item"""
        return {
            'store_code': store_code,
            'sku': self._clean_text(row.get('sku')),
            'product_name': self._clean_text(row.get('product_name')),
            'brand': self._clean_text(row.get('brand')),
            'barcode': self._clean_text(row.get('barcode')),
            'sales_qty_7d': self._parse_float(row.get('sales_qty_7d'), 0.0),
            'percent_orders': self._parse_percentage(row.get('percent_orders')),
            'percent_stops': self._parse_percentage(row.get('percent_stops')),
            'abc_class': self._clean_text(row.get('abc_class')),
            'rank': self._parse_int(row.get('rank'), 999),
        }
    
    def _clean_text(self, value: Any) -> str:
        """Clean text field"""
        if pd.isna(value) or value is None:
            return ''
        
        text = str(value).strip()
        
        if text.lower() in ['nan', 'none', 'null', '#n/a']:
            return ''
        
        return text
    
    def _parse_float(self, value: Any, default: float = 0.0) -> float:
        """Parse float field"""
        if pd.isna(value) or value is None or value == '':
            return default
        
        try:
            if isinstance(value, str):
                # Remove commas, % signs
                value = value.replace(',', '.').replace('%', '').strip()
            return float(value)
        except:
            return default
    
    def _parse_percentage(self, value: Any) -> float:
        """Parse percentage field (can be 0.15 or 15%)"""
        if pd.isna(value) or value is None or value == '':
            return 0.0
        
        try:
            if isinstance(value, str):
                value = value.replace(',', '.').replace('%', '').strip()
            
            num = float(value)
            
            # If > 1, assume it's already percentage (15.5)
            # If <= 1, assume it's decimal (0.155)
            if num > 1:
                return num
            else:
                return num * 100  # Convert to percentage
        except:
            return 0.0
    
    def _parse_int(self, value: Any, default: int = 0) -> int:
        """Parse int field"""
        if pd.isna(value) or value is None or value == '':
            return default
        
        try:
            return int(float(value))
        except:
            return default
    
    def _calculate_abc_classes(self, items: List[Dict]) -> List[Dict]:
        """
        Calculate ABC classes based on sales if not provided
        
        ABC Classification:
        - A: Top 20% of sales (cumulative 80% revenue)
        - B: Next 30% of sales (cumulative 15% revenue)
        - C: Remaining 50% of sales (cumulative 5% revenue)
        """
        # Sort by sales descending
        sorted_items = sorted(items, key=lambda x: -x.get('sales_qty_7d', 0))
        
        total_sales = sum(item.get('sales_qty_7d', 0) for item in sorted_items)
        
        if total_sales == 0:
            # No sales data, assign based on rank
            for idx, item in enumerate(sorted_items):
                if idx < len(sorted_items) * 0.2:
                    item['abc_class'] = 'A'
                elif idx < len(sorted_items) * 0.5:
                    item['abc_class'] = 'B'
                else:
                    item['abc_class'] = 'C'
            return items
        
        cumulative_sales = 0
        for item in sorted_items:
            cumulative_sales += item.get('sales_qty_7d', 0)
            cumulative_percent = (cumulative_sales / total_sales) * 100
            
            if cumulative_percent <= 80:
                item['abc_class'] = 'A'
            elif cumulative_percent <= 95:
                item['abc_class'] = 'B'
            else:
                item['abc_class'] = 'C'
        
        return items
    
    def _calculate_summary(self, items: List[Dict]) -> Dict[str, Any]:
        """Calculate ABC report summary statistics"""
        total = len(items)
        
        total_sales = sum(item.get('sales_qty_7d', 0) for item in items)
        
        class_counts = {
            'A': sum(1 for item in items if item.get('abc_class') == 'A'),
            'B': sum(1 for item in items if item.get('abc_class') == 'B'),
            'C': sum(1 for item in items if item.get('abc_class') == 'C'),
        }
        
        class_sales = {
            'A': sum(item.get('sales_qty_7d', 0) for item in items if item.get('abc_class') == 'A'),
            'B': sum(item.get('sales_qty_7d', 0) for item in items if item.get('abc_class') == 'B'),
            'C': sum(item.get('sales_qty_7d', 0) for item in items if item.get('abc_class') == 'C'),
        }
        
        return {
            'total_items': total,
            'total_sales_7d': total_sales,
            'class_distribution': {
                'A': {'count': class_counts['A'], 'percent': round(class_counts['A'] / max(total, 1) * 100, 1)},
                'B': {'count': class_counts['B'], 'percent': round(class_counts['B'] / max(total, 1) * 100, 1)},
                'C': {'count': class_counts['C'], 'percent': round(class_counts['C'] / max(total, 1) * 100, 1)},
            },
            'sales_distribution': {
                'A': {'sales': class_sales['A'], 'percent': round(class_sales['A'] / max(total_sales, 1) * 100, 1)},
                'B': {'sales': class_sales['B'], 'percent': round(class_sales['B'] / max(total_sales, 1) * 100, 1)},
                'C': {'sales': class_sales['C'], 'percent': round(class_sales['C'] / max(total_sales, 1) * 100, 1)},
            },
            'has_percent_orders': sum(1 for item in items if item.get('percent_orders', 0) > 0),
            'has_percent_stops': sum(1 for item in items if item.get('percent_stops', 0) > 0),
            'avg_sales_7d': round(total_sales / max(total, 1), 2),
        }


# Singleton
abc_service = ABCService()
