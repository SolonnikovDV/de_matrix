import json
import re
from pathlib import Path
import hashlib
from typing import Dict, List, Any, Optional

class MatrixImporter:
    """Импортер данных для матрицы компетенций"""
    
    def __init__(self, matrix_data_path: str, meta_data_path: str):
        self.matrix_data_path = Path(matrix_data_path)
        self.meta_data_path = Path(meta_data_path)
        self.matrix_data = self._load_json(self.matrix_data_path, {"domains": []})
        self.meta_data = self._load_json(self.meta_data_path, {
            "stack_labels": {},
            "action_tools": [],
            "action_examples": [],
            "action_templates": {},
            "ui_config": {}
        })
    
    def _load_json(self, path: Path, default: Dict) -> Dict:
        """Загружает JSON файл"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except Exception as e:
            print(f"Ошибка загрузки {path}: {e}")
            return default
    
    def _save_json(self, path: Path, data: Dict):
        """Сохраняет данные в JSON файл"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _generate_template_id(self, action_text: str) -> str:
        """Генерирует template_id на основе текста действия"""
        # Очищаем текст и преобразуем в snake_case
        text = action_text.lower()
        text = re.sub(r'[^a-zа-я0-9\s]', '', text)
        text = re.sub(r'\s+', '_', text)
        # Ограничиваем длину
        if len(text) > 50:
            text = text[:50]
        # Добавляем хеш для уникальности
        hash_obj = hashlib.md5(action_text.encode())
        short_hash = hash_obj.hexdigest()[:6]
        return f"{text}_{short_hash}"
    
    def _find_similar_template(self, action_text: str) -> Optional[str]:
        """Ищет похожий шаблон по ключевым словам"""
        action_lower = action_text.lower()
        words = set(re.findall(r'\w+', action_lower))
        stop_words = {'и', 'в', 'на', 'с', 'для', 'по', 'от', 'за', 'через', 'при', 'из', 'у', 'к', 'о', 'об'}
        words = words - stop_words
        
        best_match = None
        best_score = 0
        
        for template_id, template in self.meta_data['action_templates'].items():
            template_words = set(re.findall(r'\w+', template.get('name', '').lower()))
            common = words & template_words
            score = len(common)
            
            if score > best_score:
                best_score = score
                best_match = template_id
        
        return best_match if best_score >= 2 else None
    
    def import_from_json(self, json_path: str, domain_mapping: Dict[str, str] = None):
        """
        Импортирует данные из JSON файла
        
        Args:
            json_path: путь к JSON файлу для импорта
            domain_mapping: маппинг названий доменов (если названия отличаются)
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        return self._process_import_data(import_data, domain_mapping)
    
    def import_from_xlsx(self, xlsx_path: str, sheet_name: str = 'Sheet1'):
        """
        Импортирует данные из XLSX файла
        Требует установки: pip install openpyxl pandas
        """
        try:
            import pandas as pd
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
            return self._process_dataframe(df)
        except ImportError:
            print("Для импорта XLSX установите: pip install openpyxl pandas")
            return None
    
    def import_from_csv(self, csv_path: str, delimiter: str = ','):
        """
        Импортирует данные из CSV файла
        Требует установки: pip install pandas
        """
        try:
            import pandas as pd
            df = pd.read_csv(csv_path, delimiter=delimiter)
            return self._process_dataframe(df)
        except ImportError:
            print("Для импорта CSV установите: pip install pandas")
            return None
    
    def _process_dataframe(self, df):
        """Обрабатывает DataFrame из pandas"""
        # Ожидаемая структура: domain | skill | action | description | requirements | antipatterns
        imported_count = 0
        new_templates = 0
        
        for _, row in df.iterrows():
            domain_name = str(row.get('domain', '')).strip()
            skill_name = str(row.get('skill', '')).strip()
            action_text = str(row.get('action', '')).strip()
            
            if not all([domain_name, skill_name, action_text]):
                continue
            
            # Находим или создаем домен
            domain = self._find_or_create_domain(domain_name)
            
            # Находим или создаем навык
            skill = self._find_or_create_skill(domain, skill_name)
            
            # Проверяем, есть ли уже такое действие
            existing_action = self._find_action(skill, action_text)
            
            if existing_action:
                # Обновляем существующее действие
                if 'description' in row and pd.notna(row['description']):
                    # Создаем или обновляем шаблон
                    template_id = existing_action.get('template_id')
                    if template_id and template_id in self.meta_data['action_templates']:
                        template = self.meta_data['action_templates'][template_id]
                        if 'minimal_requirements' not in template:
                            template['minimal_requirements'] = []
                        if 'antipatterns' not in template:
                            template['antipatterns'] = []
                        
                        # Добавляем новые требования
                        if pd.notna(row.get('requirements')):
                            reqs = str(row['requirements']).split('\n')
                            template['minimal_requirements'].extend([r for r in reqs if r.strip()])
                        
                        if pd.notna(row.get('antipatterns')):
                            ants = str(row['antipatterns']).split('\n')
                            template['antipatterns'].extend([a for a in ants if a.strip()])
            else:
                # Создаем новое действие
                template_id = self._find_similar_template(action_text)
                
                if not template_id:
                    # Создаем новый шаблон
                    template_id = self._generate_template_id(action_text)
                    self.meta_data['action_templates'][template_id] = {
                        'name': action_text[:50],
                        'minimal_requirements': [],
                        'antipatterns': []
                    }
                    
                    # Добавляем требования если есть
                    if pd.notna(row.get('requirements')):
                        reqs = str(row['requirements']).split('\n')
                        self.meta_data['action_templates'][template_id]['minimal_requirements'] = [
                            r for r in reqs if r.strip()
                        ]
                    
                    if pd.notna(row.get('antipatterns')):
                        ants = str(row['antipatterns']).split('\n')
                        self.meta_data['action_templates'][template_id]['antipatterns'] = [
                            a for a in ants if a.strip()
                        ]
                    
                    new_templates += 1
                
                # Добавляем действие в навык
                if 'actions' not in skill:
                    skill['actions'] = []
                
                skill['actions'].append({
                    'text': action_text,
                    'template_id': template_id
                })
                imported_count += 1
        
        return {
            'imported_actions': imported_count,
            'new_templates': new_templates
        }
    
    def _process_import_data(self, import_data: Dict, domain_mapping: Dict[str, str] = None):
        """Обрабатывает импортированные данные в формате JSON"""
        imported_count = 0
        new_templates = 0
        
        for domain_data in import_data.get('domains', []):
            domain_name = domain_data['name']
            if domain_mapping and domain_name in domain_mapping:
                domain_name = domain_mapping[domain_name]
            
            domain = self._find_or_create_domain(domain_name)
            
            for skill_data in domain_data.get('skills', []):
                skill_name = skill_data['name']
                skill = self._find_or_create_skill(domain, skill_name)
                
                # Обновляем описание навыка если есть
                if 'description' in skill_data and not skill.get('description'):
                    skill['description'] = skill_data['description']
                
                for action_data in skill_data.get('actions', []):
                    if isinstance(action_data, str):
                        # Просто текст действия
                        action_text = action_data
                        template_id = self._find_similar_template(action_text)
                        
                        if not template_id:
                            template_id = self._generate_template_id(action_text)
                            self.meta_data['action_templates'][template_id] = {
                                'name': action_text[:50],
                                'minimal_requirements': [],
                                'antipatterns': []
                            }
                            new_templates += 1
                        
                        if not self._find_action(skill, action_text):
                            skill.setdefault('actions', []).append({
                                'text': action_text,
                                'template_id': template_id
                            })
                            imported_count += 1
                    
                    elif isinstance(action_data, dict):
                        # Действие с дополнительными данными
                        action_text = action_data['text']
                        template_id = action_data.get('template_id')
                        
                        if not template_id:
                            template_id = self._find_similar_template(action_text)
                        
                        if not template_id:
                            template_id = self._generate_template_id(action_text)
                            self.meta_data['action_templates'][template_id] = {
                                'name': action_text[:50],
                                'minimal_requirements': action_data.get('minimal_requirements', []),
                                'antipatterns': action_data.get('antipatterns', [])
                            }
                            new_templates += 1
                        elif template_id in self.meta_data['action_templates']:
                            # Обновляем существующий шаблон
                            template = self.meta_data['action_templates'][template_id]
                            if 'minimal_requirements' in action_data:
                                template['minimal_requirements'] = action_data['minimal_requirements']
                            if 'antipatterns' in action_data:
                                template['antipatterns'] = action_data['antipatterns']
                        
                        if not self._find_action(skill, action_text):
                            skill.setdefault('actions', []).append({
                                'text': action_text,
                                'template_id': template_id
                            })
                            imported_count += 1
        
        return {
            'imported_actions': imported_count,
            'new_templates': new_templates
        }
    
    def _find_or_create_domain(self, domain_name: str) -> Dict:
        """Находит или создает домен"""
        for domain in self.matrix_data['domains']:
            if domain['name'] == domain_name:
                return domain
        
        # Создаем новый домен
        new_domain = {
            'name': domain_name,
            'skills': []
        }
        self.matrix_data['domains'].append(new_domain)
        return new_domain
    
    def _find_or_create_skill(self, domain: Dict, skill_name: str) -> Dict:
        """Находит или создает навык в домене"""
        for skill in domain.get('skills', []):
            if skill['name'] == skill_name:
                return skill
        
        # Создаем новый навык
        new_skill = {
            'name': skill_name,
            'description': '',
            'actions': []
        }
        domain.setdefault('skills', []).append(new_skill)
        return new_skill
    
    def _find_action(self, skill: Dict, action_text: str) -> Optional[Dict]:
        """Находит действие по тексту"""
        for action in skill.get('actions', []):
            if action['text'] == action_text:
                return action
        return None
    
    def save(self):
        """Сохраняет изменения в файлы"""
        self._save_json(self.matrix_data_path, self.matrix_data)
        self._save_json(self.meta_data_path, self.meta_data)
        print(f"✅ Данные сохранены:")
        print(f"   - matrix_data.json: {len(self.matrix_data['domains'])} доменов")
        print(f"   - meta.json: {len(self.meta_data['action_templates'])} шаблонов")