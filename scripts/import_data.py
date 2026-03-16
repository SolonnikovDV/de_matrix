#!/usr/bin/env python3
"""
Скрипт для импорта данных в матрицу компетенций
Использование:
    python scripts/import_data.py --file data/new_actions.json
    python scripts/import_data.py --file data/new_actions.xlsx --sheet Лист1
    python scripts/import_data.py --file data/new_actions.csv --delimiter ";"
"""

import argparse
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent))

from utils.importer import MatrixImporter

def main():
    parser = argparse.ArgumentParser(description='Импорт данных в матрицу компетенций')
    parser.add_argument('--file', required=True, help='Путь к файлу для импорта')
    parser.add_argument('--format', choices=['json', 'xlsx', 'csv', 'auto'], 
                       default='auto', help='Формат файла')
    parser.add_argument('--sheet', default='Sheet1', help='Название листа для XLSX')
    parser.add_argument('--delimiter', default=',', help='Разделитель для CSV')
    parser.add_argument('--mapping', help='JSON файл с маппингом названий доменов')
    
    args = parser.parse_args()
    
    # Определяем формат файла
    file_path = Path(args.file)
    if args.format == 'auto':
        if file_path.suffix.lower() == '.json':
            fmt = 'json'
        elif file_path.suffix.lower() in ['.xlsx', '.xls']:
            fmt = 'xlsx'
        elif file_path.suffix.lower() == '.csv':
            fmt = 'csv'
        else:
            print(f"❌ Не удалось определить формат файла {file_path}")
            return
    else:
        fmt = args.format
    
    # Загружаем маппинг если есть
    domain_mapping = None
    if args.mapping:
        with open(args.mapping, 'r', encoding='utf-8') as f:
            domain_mapping = json.load(f)
    
    # Создаем импортер
    importer = MatrixImporter(
        matrix_data_path='data/matrix_data.json',
        meta_data_path='config/meta.json'
    )
    
    # Импортируем данные
    print(f"📥 Импорт из файла: {file_path}")
    
    try:
        if fmt == 'json':
            result = importer.import_from_json(str(file_path), domain_mapping)
        elif fmt == 'xlsx':
            result = importer.import_from_xlsx(str(file_path), args.sheet)
        elif fmt == 'csv':
            result = importer.import_from_csv(str(file_path), args.delimiter)
        
        if result:
            print(f"\n✅ Результат импорта:")
            print(f"   - Импортировано действий: {result['imported_actions']}")
            print(f"   - Создано новых шаблонов: {result['new_templates']}")
            
            # Сохраняем изменения
            importer.save()
            
            print(f"\n🚀 Перезапустите приложение для применения изменений")
        else:
            print("❌ Импорт не удался")
            
    except Exception as e:
        print(f"❌ Ошибка при импорте: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()