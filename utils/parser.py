import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import hashlib

class MatrixDataParser:
    """
    Универсальный парсер для импорта данных в структуру матрицы компетенций.
    Поддерживает различные форматы входных данных и раскладывает их в target структуру.
    """
    
    def __init__(self, matrix_data_path: str, meta_path: str):
        self.matrix_data_path = Path(matrix_data_path)
        self.meta_path = Path(meta_path)
        self.matrix_data = self._load_json(self.matrix_data_path, {"domains": []})
        self.meta = self._load_json(self.meta_path, {
            "stack_labels": {},
            "action_tools": [],
            "action_examples": [],
            "action_templates": {},
            "ui_config": {}
        })
        
        # Кэши для быстрого поиска
        self._domain_cache = {d['name']: d for d in self.matrix_data['domains']}
        self._template_cache = self.meta['action_templates']
        self._tools_cache = {t['id']: t for t in self.meta['action_tools'] if 'id' in t}
        self._examples_cache = {e['id']: e for e in self.meta['action_examples'] if 'id' in e}
        self._stack_cache = self.meta['stack_labels']
    
    def _load_json(self, path: Path, default: Dict) -> Dict:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception as e:
            print(f"Ошибка загрузки {path}: {e}")
            return default
    
    def _save_json(self, path: Path, data: Dict):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _generate_id(self, text: str, prefix: str = "") -> str:
        """Генерирует ID из текста"""
        clean = re.sub(r'[^a-zA-Z0-9]', '_', text.lower())
        clean = re.sub(r'_+', '_', clean).strip('_')
        if len(clean) > 30:
            clean = clean[:30]
        hash_obj = hashlib.md5(text.encode())
        short_hash = hash_obj.hexdigest()[:4]
        return f"{prefix}_{clean}_{short_hash}" if prefix else f"{clean}_{short_hash}"
    
    def _find_or_create_domain(self, domain_name: str) -> Dict:
        """Находит или создает домен"""
        if domain_name in self._domain_cache:
            return self._domain_cache[domain_name]
        
        new_domain = {
            'name': domain_name,
            'skills': []
        }
        self.matrix_data['domains'].append(new_domain)
        self._domain_cache[domain_name] = new_domain
        return new_domain
    
    def _find_or_create_skill(self, domain: Dict, skill_name: str, description: str = "") -> Dict:
        """Находит или создает навык в домене"""
        for skill in domain.get('skills', []):
            if skill['name'] == skill_name:
                if description and not skill.get('description'):
                    skill['description'] = description
                return skill
        
        new_skill = {
            'name': skill_name,
            'description': description,
            'actions': []
        }
        domain.setdefault('skills', []).append(new_skill)
        return new_skill
    
    def _find_or_create_template(self, action_data: Dict) -> str:
        """
        Находит существующий шаблон или создает новый.
        action_data может содержать:
        - text: текст действия
        - minimal_requirements: список требований
        - antipatterns: список антипаттернов
        - stack_refs: ссылки на стек
        - tools_refs: ссылки на инструменты
        - examples_refs: ссылки на примеры
        """
        action_text = action_data.get('text', '')
        
        # Ищем похожий шаблон по тексту
        best_match = None
        best_score = 0
        
        for tid, template in self._template_cache.items():
            template_name = template.get('name', '').lower()
            # Ищем совпадения в названии шаблона и тексте действия
            words = set(re.findall(r'\w+', action_text.lower()))
            template_words = set(re.findall(r'\w+', template_name))
            common = words & template_words
            score = len(common)
            
            if score > best_score:
                best_score = score
                best_match = tid
        
        # Если нашли хорошее совпадение, используем его
        if best_score >= 2:
            template = self._template_cache[best_match]
            # Дополняем существующий шаблон новыми данными
            if 'minimal_requirements' in action_data:
                new_reqs = action_data['minimal_requirements']
                existing = template.setdefault('minimal_requirements', [])
                for req in new_reqs:
                    if req not in existing:
                        existing.append(req)
            
            if 'antipatterns' in action_data:
                new_ants = action_data['antipatterns']
                existing = template.setdefault('antipatterns', [])
                for ant in new_ants:
                    if ant not in existing:
                        existing.append(ant)
            
            if 'stack_refs' in action_data:
                template['stack_refs'] = list(set(template.get('stack_refs', []) + action_data['stack_refs']))
            
            if 'tools_refs' in action_data:
                template['tools_refs'] = list(set(template.get('tools_refs', []) + action_data['tools_refs']))
            
            return best_match
        
        # Создаем новый шаблон
        template_id = self._generate_id(action_text, "tpl")
        new_template = {
            'name': action_text[:50],
            'minimal_requirements': action_data.get('minimal_requirements', []),
            'antipatterns': action_data.get('antipatterns', []),
            'stack_refs': action_data.get('stack_refs', []),
            'tools_refs': action_data.get('tools_refs', []),
            'examples_refs': action_data.get('examples_refs', [])
        }
        self._template_cache[template_id] = new_template
        return template_id
    
    def _extract_stack_refs(self, text: str) -> List[str]:
        """Извлекает ссылки на стек из текста действия"""
        stack_refs = []
        text_lower = text.lower()
        for stack_id, stack_data in self._stack_cache.items():
            if stack_id in text_lower or stack_data['name'].lower() in text_lower:
                stack_refs.append(stack_id)
        return stack_refs
    
    def _extract_tools_refs(self, text: str) -> List[str]:
        """Извлекает ссылки на инструменты из текста действия"""
        tools_refs = []
        text_lower = text.lower()
        for tool_id, tool_data in self._tools_cache.items():
            for tool_name in tool_data.get('tools', []):
                if tool_name.lower() in text_lower:
                    tools_refs.append(tool_id)
                    break
        return tools_refs
    
    def parse_json(self, json_data: Union[Dict, str]) -> Dict:
        """
        Парсит JSON данные и раскладывает в target структуру.
        Поддерживает разные форматы:
        1. Прямое соответствие нашей структуре
        2. Упрощенная структура с массивами строк
        3. Плоская структура с колонками
        """
        if isinstance(json_data, str):
            json_data = json.loads(json_data)
        
        stats = {
            'domains_created': 0,
            'skills_created': 0,
            'actions_added': 0,
            'templates_created': 0
        }
        
        # Формат 1: наша структура (домены -> навыки -> действия)
        if 'domains' in json_data:
            for domain_data in json_data['domains']:
                domain = self._find_or_create_domain(domain_data['name'])
                stats['domains_created'] += 1
                
                for skill_data in domain_data.get('skills', []):
                    skill = self._find_or_create_skill(
                        domain, 
                        skill_data['name'],
                        skill_data.get('description', '')
                    )
                    stats['skills_created'] += 1
                    
                    for action_data in skill_data.get('actions', []):
                        if isinstance(action_data, str):
                            # Просто строка действия
                            action_text = action_data
                            template_id = self._find_or_create_template({'text': action_text})
                        else:
                            # Действие с данными
                            action_text = action_data['text']
                            template_id = self._find_or_create_template(action_data)
                        
                        # Проверяем, нет ли уже такого действия
                        if not any(a['text'] == action_text for a in skill['actions']):
                            skill['actions'].append({
                                'text': action_text,
                                'template_id': template_id
                            })
                            stats['actions_added'] += 1
        
        # Формат 2: плоская структура (список действий с метаданными)
        elif 'actions' in json_data:
            for action_item in json_data['actions']:
                domain_name = action_item.get('domain', 'Общее')
                skill_name = action_item.get('skill', 'Общие навыки')
                action_text = action_item.get('action', '')
                
                if not action_text:
                    continue
                
                domain = self._find_or_create_domain(domain_name)
                skill = self._find_or_create_skill(domain, skill_name)
                
                template_id = self._find_or_create_template({
                    'text': action_text,
                    'minimal_requirements': action_item.get('requirements', []),
                    'antipatterns': action_item.get('antipatterns', []),
                    'stack_refs': action_item.get('stack_refs', []),
                    'tools_refs': action_item.get('tools_refs', [])
                })
                
                if not any(a['text'] == action_text for a in skill['actions']):
                    skill['actions'].append({
                        'text': action_text,
                        'template_id': template_id
                    })
                    stats['actions_added'] += 1
        
        # Формат 3: CSV-like структура (колонки)
        elif 'rows' in json_data:
            for row in json_data['rows']:
                domain_name = row.get(0, 'Общее')
                skill_name = row.get(1, 'Общие навыки')
                action_text = row.get(2, '')
                
                if not action_text:
                    continue
                
                domain = self._find_or_create_domain(domain_name)
                skill = self._find_or_create_skill(domain, skill_name)
                
                # Пробуем извлечь стек из текста
                stack_refs = self._extract_stack_refs(action_text)
                tools_refs = self._extract_tools_refs(action_text)
                
                template_id = self._find_or_create_template({
                    'text': action_text,
                    'stack_refs': stack_refs,
                    'tools_refs': tools_refs
                })
                
                if not any(a['text'] == action_text for a in skill['actions']):
                    skill['actions'].append({
                        'text': action_text,
                        'template_id': template_id
                    })
                    stats['actions_added'] += 1
        
        # Обновляем кэши
        self._domain_cache = {d['name']: d for d in self.matrix_data['domains']}
        
        return stats
    
    def parse_xlsx(self, file_path: str, sheet_name: str = 'Sheet1') -> Dict:
        """Парсит XLSX файл и раскладывает в структуру"""
        try:
            import pandas as pd
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            # Преобразуем в JSON и парсим
            data = {'actions': []}
            for _, row in df.iterrows():
                action_item = {}
                for col in df.columns:
                    value = row[col]
                    if pd.notna(value):
                        if col == 'requirements' or col == 'antipatterns':
                            # Разбиваем по строкам
                            action_item[col] = [v.strip() for v in str(value).split('\n') if v.strip()]
                        else:
                            action_item[col] = str(value).strip()
                data['actions'].append(action_item)
            
            return self.parse_json(data)
        except ImportError:
            print("Для импорта XLSX установите: pip install pandas openpyxl")
            return {'error': 'pandas not installed'}
        except Exception as e:
            print(f"Ошибка парсинга XLSX: {e}")
            return {'error': str(e)}
    
    def parse_csv(self, file_path: str, delimiter: str = ',') -> Dict:
        """Парсит CSV файл и раскладывает в структуру"""
        try:
            import pandas as pd
            df = pd.read_csv(file_path, delimiter=delimiter)
            
            data = {'actions': []}
            for _, row in df.iterrows():
                action_item = {}
                for col in df.columns:
                    value = row[col]
                    if pd.notna(value):
                        if col == 'requirements' or col == 'antipatterns':
                            action_item[col] = [v.strip() for v in str(value).split('\n') if v.strip()]
                        else:
                            action_item[col] = str(value).strip()
                data['actions'].append(action_item)
            
            return self.parse_json(data)
        except ImportError:
            print("Для импорта CSV установите: pip install pandas")
            return {'error': 'pandas not installed'}
        except Exception as e:
            print(f"Ошибка парсинга CSV: {e}")
            return {'error': str(e)}
    
    def save(self):
        """Сохраняет изменения в файлы"""
        # Обновляем meta с новыми шаблонами
        self.meta['action_templates'] = self._template_cache
        
        self._save_json(self.matrix_data_path, self.matrix_data)
        self._save_json(self.meta_path, self.meta)
        
        print(f"\n✅ Данные сохранены:")
        print(f"   - matrix_data.json: {len(self.matrix_data['domains'])} доменов")
        print(f"   - meta.json: {len(self._template_cache)} шаблонов")

# CLI интерфейс
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Импорт данных в матрицу компетенций')
    parser.add_argument('--file', required=True, help='Путь к файлу для импорта')
    parser.add_argument('--format', choices=['json', 'xlsx', 'csv'], default='json',
                       help='Формат файла')
    parser.add_argument('--sheet', default='Sheet1', help='Название листа для XLSX')
    parser.add_argument('--delimiter', default=',', help='Разделитель для CSV')
    
    args = parser.parse_args()
    
    importer = MatrixDataParser('data/matrix_data.json', 'config/meta.json')
    
    if args.format == 'json':
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        stats = importer.parse_json(data)
    elif args.format == 'xlsx':
        stats = importer.parse_xlsx(args.file, args.sheet)
    elif args.format == 'csv':
        stats = importer.parse_csv(args.file, args.delimiter)
    
    if stats and 'error' not in stats:
        print(f"\n📊 Результат импорта:")
        for key, value in stats.items():
            print(f"   - {key}: {value}")
        
        importer.save()
    else:
        print(f"❌ Ошибка импорта: {stats.get('error', 'неизвестная ошибка')}")

"""
1. Импорт из JSON в нашем формате:
bash
python utils/parser.py --file data/new_actions.json
2. Импорт из XLSX:
bash
python utils/parser.py --file data/new_actions.xlsx --format xlsx --sheet "Actions"
3. Импорт из CSV:
bash
python utils/parser.py --file data/new_actions.csv --format csv --delimiter ";"


Пример структуры для импорта:
Простой JSON:
json
{
  "actions": [
    {
      "domain": "Хранение и управление данными",
      "skill": "Моделирование данных",
      "action": "Новое действие по моделированию",
      "requirements": [
        "🔹 Требование 1",
        "🔹 Требование 2"
      ],
      "antipatterns": [
        "❌ Антипаттерн 1",
        "❌ Антипаттерн 2"
      ]
    }
  ]
}

"""