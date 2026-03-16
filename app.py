import json
import os
import re
import hashlib
import sys
import argparse
import socket
from flask import Flask, render_template, jsonify, abort, send_from_directory, request

from pathlib import Path as PathLib

from core.tree import (
    build_tree_from_matrix_data,
    collect_leaves,
    get_node_by_path,
    get_ancestors,
    path_to_url,
)
from core.loaders import load_unified_source, load_unified_source_with_validation, load_excel, META_KEYS
from core.schema import SCHEMA_VERSION, validate_source, get_schema_info
from core import config_loader as _config_loader
from core.config_loader import load_app_config, load_metadata, invalidate_metadata_cache
from core.tools_matcher import get_tools_for_text
from core.checkpoint import (
    load_checkpoint,
    save_checkpoint,
    source_matches_checkpoint,
    build_checkpoint_data,
    get_source_content_hash,
)
from core.backup import create_backup, list_backups, restore_backup, check_backup_compatibility
from core.upload_merge import merge_upload_into_source

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Путь к config — гарантированно относительно app.py (для metadata.yaml: stack_labels, tools)
_config_loader.CONFIG_DIR = PathLib(BASE_DIR) / "config"

_matrix = None
_meta = None
_tree = None
_current_source_file = None  # имя файла-источника, по которому загружены данные


def _literature_dir():
    """Каталог для скачанной литературы (data/library)."""
    cfg = get_meta()
    rel = cfg.get('literature_dir') or cfg.get('library_dir') or 'data/library'
    path = os.path.join(BASE_DIR, rel) if not os.path.isabs(rel) else rel
    os.makedirs(path, exist_ok=True)
    return path


def _invalidate_caches():
    """Сброс кэшей: при перезапуске или изменении источника данные перезагружаются (autoscale)."""
    global _matrix, _meta, _tree, _current_source_file
    _matrix = None
    _meta = None
    _tree = None
    _current_source_file = None
    invalidate_metadata_cache()


def _path_config():
    """Только настройки путей (без мета из источника). Используется до загрузки данных."""
    return load_app_config()


def _source_dir_path():
    """Абсолютный путь к каталогу источников (source_dir из настроек)."""
    cfg = _meta if _meta is not None else _path_config()
    rel = cfg.get("source_dir") or "data/sources"
    path = os.path.join(BASE_DIR, rel) if not os.path.isabs(rel) else rel
    return path


def _checkpoint_path():
    """Абсолютный путь к файлу чекпоинта."""
    cfg = _meta if _meta is not None else _path_config()
    rel = cfg.get("checkpoint_file") or "data/checkpoint.yaml"
    path = os.path.join(BASE_DIR, rel) if not os.path.isabs(rel) else rel
    return path


def _list_source_files():
    """Список имён файлов-источников в source_dir (JSON, YAML, Excel)."""
    allowed = (".json", ".yaml", ".yml", ".xlsx", ".xls")
    src_dir = _source_dir_path()
    if not os.path.isdir(src_dir):
        return []
    return sorted(
        f for f in os.listdir(src_dir)
        if os.path.isfile(os.path.join(src_dir, f)) and f.lower().endswith(allowed)
    )


def _current_source_for_backup() -> str:
    """Имя текущего файла-источника для бэкапа (чекпоинт или default)."""
    global _current_source_file
    if _current_source_file:
        return _current_source_file
    cfg = _path_config()
    checkpoint = load_checkpoint(PathLib(_checkpoint_path()))
    if checkpoint and checkpoint.get("source_file"):
        return checkpoint["source_file"]
    default = cfg.get("default_source")
    candidates = _list_source_files()
    if default and default in candidates:
        return default
    return candidates[0] if candidates else ""


def _ensure_data_loaded(force_source_filename: str = None):
    """
    Загружает данные из единого источника: при совпадении с чекпоинтом — из чекпоинта;
    иначе — из файла (структура + мета), пересборка дерева и сохранение чекпоинта.
    Мета (шаблоны, литература, стек и т.д.) берётся только из этого источника.
    """
    global _matrix, _tree, _meta, _current_source_file
    if _matrix is not None and _tree is not None and not force_source_filename:
        return
    path_cfg = _path_config()
    source_dir = _source_dir_path()
    checkpoint_path = _checkpoint_path()
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    os.makedirs(source_dir, exist_ok=True)

    checkpoint = load_checkpoint(PathLib(checkpoint_path))
    if force_source_filename:
        source_file = force_source_filename
    elif checkpoint and checkpoint.get("source_file"):
        source_file = checkpoint["source_file"]
    else:
        default = path_cfg.get("default_source")
        candidates = _list_source_files()
        source_file = default if default and default in candidates else (candidates[0] if candidates else None)

    if not source_file:
        _matrix = {"domains": []}
        _tree = []
        _meta = {**path_cfg, **{k: {} if k != "action_examples" else [] for k in META_KEYS}}
        return

    source_path = os.path.join(source_dir, source_file)
    if not os.path.isfile(source_path):
        _matrix = {"domains": []}
        _tree = []
        _meta = {**path_cfg, **{k: {} if k != "action_examples" else [] for k in META_KEYS}}
        return

    # Совпадает ли источник с чекпоинтом? Используем чекпоинт только если в нём есть полный meta (action_templates, literature).
    meta_from_checkpoint = (checkpoint or {}).get("meta")
    if isinstance(meta_from_checkpoint, dict):
        pass
    else:
        meta_from_checkpoint = {}
    has_meta = bool(meta_from_checkpoint.get("action_templates") or meta_from_checkpoint.get("literature"))
    if (
        checkpoint
        and checkpoint.get("source_file") == source_file
        and source_matches_checkpoint(PathLib(source_path), checkpoint)
        and has_meta
    ):
        _matrix = checkpoint.get("matrix") or {"domains": []}
        _tree = checkpoint.get("tree") or []
        _meta = {**path_cfg, **meta_from_checkpoint}
        _current_source_file = source_file
        return

    # Перезагрузка из единого источника: структура + мета в одном файле
    try:
        unified = load_unified_source(source_path)
    except Exception as e:
        print(f"Ошибка загрузки источника {source_path}: {e}")
        _matrix = {"domains": []}
        _tree = []
        _meta = {**path_cfg, **{k: {} if k != "action_examples" else [] for k in META_KEYS}}
        return
    domains = unified.get("domains") or []
    _matrix = {"domains": domains}
    _tree = build_tree_from_matrix_data(_matrix)
    meta_from_source = {k: unified.get(k, {} if k != "action_examples" else []) for k in META_KEYS}
    _meta = {**path_cfg, **meta_from_source}
    source_hash = get_source_content_hash(PathLib(source_path))
    checkpoint_data = build_checkpoint_data(_tree, _matrix, meta_from_source, source_file, source_hash)
    save_checkpoint(PathLib(checkpoint_path), checkpoint_data, use_yaml=checkpoint_path.lower().endswith((".yaml", ".yml")))
    _current_source_file = source_file

# ----- Вспомогательные функции для генерации иконок и цветов -----
DOMAIN_ICONS = [
    "database", "cloud", "code-branch", "check-circle", "users",
    "server", "chart-line", "cube", "cogs", "file-alt"
]
SKILL_ICONS = [
    "cube", "bolt", "layer-group", "fire", "clock", "python",
    "sync-alt", "chart-line", "check-double", "project-diagram", "file-alt",
    "comments", "tasks", "chalkboard-teacher"
]

def get_domain_icon(domain_name, index):
    return DOMAIN_ICONS[index % len(DOMAIN_ICONS)]

def get_skill_icon(skill_name, index):
    return SKILL_ICONS[index % len(SKILL_ICONS)]

def string_to_hsl(text, s=70, l=60):
    hash_obj = hashlib.md5(text.encode())
    hue = int(hash_obj.hexdigest()[:6], 16) % 360
    return f"hsl({hue}, {s}%, {l}%)"

def get_domain_color(domain_name):
    return string_to_hsl(domain_name, s=70, l=60)

def get_skill_color(skill_name, domain_color, skill_index):
    match = re.match(r'hsl\((\d+), (\d+)%, (\d+)%\)', domain_color)
    if match:
        hue = (int(match.group(1)) + skill_index * 30) % 360
        s = int(match.group(2))
        l = int(match.group(3))
        return f"hsl({hue}, {s}%, {l}%)"
    return domain_color

# ----------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Файл {path} не найден. Используется значение по умолчанию.")
        return default
    except Exception as e:
        print(f"Ошибка загрузки {path}: {e}")
        return default

def get_meta():
    """Конфиг: пути из settings + данные из источника (текст) + стили/инструменты из config/metadata.yaml."""
    global _meta
    if _meta is None:
        _meta = _path_config()
        _ensure_data_loaded()
    metadata = load_metadata()
    out = {
        **_meta,
        "stack_labels": metadata.get("stack_labels", {}),
        "tools_patterns": metadata.get("tools_patterns", {}),
        "tools_groups": metadata.get("tools_groups", {}),
    }
    out.setdefault("action_templates", {})
    out.setdefault("literature", {})
    out.setdefault("action_examples", [])
    out.setdefault("ui_config", {})
    return out


def get_matrix():
    """Структура матрицы из чекпоинта или файла-источника (source_dir). Сверка по хешу при каждой загрузке."""
    _ensure_data_loaded()
    return _matrix if _matrix is not None else {"domains": []}


def get_tree():
    """Дерево матрицы (autoscale по структуре источника). Листья — узлы без children."""
    _ensure_data_loaded()
    return _tree if _tree is not None else []

def save_meta(meta_dict):
    """Сохраняет метаданные в единый источник (текущий файл в source_dir). Обновляет чекпоинт при следующей загрузке."""
    global _meta
    path_cfg = _path_config()
    _meta = {**path_cfg, **meta_dict}
    source_dir = _source_dir_path()
    source_file = _current_source_file
    if not source_file:
        return
    source_path = os.path.join(source_dir, source_file)
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in (".json", ".yaml", ".yml"):
        return  # Excel не перезаписываем
    unified = {
        "schema_version": SCHEMA_VERSION,
        "domains": (get_matrix() or {}).get("domains", []),
        **{k: meta_dict.get(k, {} if k != "action_examples" else []) for k in META_KEYS},
    }
    try:
        if ext == ".json":
            with open(source_path, "w", encoding="utf-8") as f:
                json.dump(unified, f, ensure_ascii=False, indent=2)
        else:
            import yaml
            with open(source_path, "w", encoding="utf-8") as f:
                yaml.dump(unified, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        _invalidate_caches()
    except Exception as e:
        print(f"Ошибка сохранения в источник {source_path}: {e}")

def slugify(text):
    if not text:
        return ''
    return re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')

def find_free_port(start_port=5000, max_attempts=10):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return None

def enrich_action(action_obj, template, meta):
    """Обогащает действие: стек по stack_refs из шаблона (стили из config), инструменты — по паттернам в тексте."""
    stack_labels = meta.get("stack_labels", {})
    action_examples = meta.get("action_examples", [])
    literature = meta.get("literature", {})
    tools_patterns = meta.get("tools_patterns", {})
    tools_groups = meta.get("tools_groups", {})

    if not template:
        return {
            "stack_labels": [],
            "tools": [],
            "examples": [],
            "literature": [],
        }

    stack_refs = template.get("stack_refs", [])
    resolved_stack = [{"key": ref, **stack_labels[ref]} for ref in stack_refs if ref in stack_labels]

    leaf_text = (action_obj.get("text") or action_obj.get("name") or "")
    template_text = " ".join(template.get("minimal_requirements") or []) + " " + " ".join(template.get("antipatterns") or [])
    resolved_tools = get_tools_for_text(leaf_text, template_text, tools_patterns, tools_groups)

    examples_refs = template.get("examples_refs", [])
    examples_by_id = {e['id']: e for e in action_examples if 'id' in e}
    resolved_examples = []
    for ref in examples_refs:
        if ref in examples_by_id:
            ex = examples_by_id[ref]
            code = ex.get('code', '').replace('<', '&lt;').replace('>', '&gt;')
            resolved_examples.append({
                'html': f'<pre><code class="language-{ex.get("language", "sql")}">{code}</code></pre>',
                'title': ex.get('title', '')
            })
    
    resource_ids = template.get('resource_ids', [])
    resolved_literature = []
    for rid in resource_ids:
        if rid in literature:
            resolved_literature.append(literature[rid])
    
    return {
        'stack_labels': resolved_stack,
        'tools': resolved_tools,
        'examples': resolved_examples,
        'literature': resolved_literature
    }

def build_description(action_obj, template, domain, skill, meta):
    minimal = template.get('minimal_requirements', [])
    antipatterns = template.get('antipatterns', [])
    ui = meta.get('ui_config', {})
    titles = ui.get('section_titles', {})

    if not minimal and not antipatterns:
        return f"""
            <h4>📋 Действие в контексте {domain['name']}</h4>
            <p><strong>{action_obj['text']}</strong> относится к навыку <strong>{skill['name']}</strong>.</p>
            <p>Описание пока не добавлено.</p>
        """

    html = f"<h4>📋 {template.get('name', 'Действие')}</h4>"
    if minimal:
        html += f"<h5>✅ {titles.get('minimal_requirements', 'Минимальный объем')}:</h5><ul>"
        for req in minimal:
            html += f"<li>{req}</li>"
        html += "</ul>"
    if antipatterns:
        html += f"<h5>⚠️ {titles.get('antipatterns', 'Антипаттерны')}:</h5><ul>"
        for anti in antipatterns:
            html += f"<li>{anti}</li>"
        html += "</ul>"
    html += f"<p><small>Контекст: <strong>{domain['name']}</strong> → <strong>{skill['name']}</strong></small></p>"
    return html

def resolve_leaf_by_path(path_str):
    """
    По path (например "0/1/2" или "0/1/2/0") возвращает (domain, skill, action, parent_action_text)
    для рендера страницы листа. action — dict с text, template_id; domain/skill — dict с name, description у skill.
    Если узел не найден или не лист — возвращает None.
    """
    try:
        path = [int(x) for x in path_str.strip("/").split("/") if x.strip()]
    except (ValueError, AttributeError):
        return None
    if not path:
        return None
    tree = get_tree()
    node = get_node_by_path(tree, path)
    if not node or node.get("children"):
        return None
    ancestors = get_ancestors(tree, path)
    if len(ancestors) < 2:
        return None
    domain = {"name": ancestors[0].get("name", "")}
    skill = {"name": ancestors[1].get("name", ""), "description": ancestors[1].get("description", "")}
    action = {"text": node.get("name", ""), "template_id": node.get("template_id")}
    parent_action_text = ancestors[2].get("name", "") if len(ancestors) > 3 else None
    return (domain, skill, action, parent_action_text)

def find_related_skills(data, domain_idx, skill_idx, action_idx):
    related = []
    try:
        current_domain = data['domains'][domain_idx]
        current_skill = current_domain['skills'][skill_idx]
        current_action = current_skill['actions'][action_idx]
        current_text = current_action.get('text', '').lower()
        words = set(re.findall(r'\w+', current_text))
        stop_words = {'и', 'в', 'на', 'с', 'для', 'по', 'от', 'за', 'через', 'при', 'из', 'у', 'к', 'о', 'об'}
        words = words - stop_words

        for di, d in enumerate(data['domains']):
            for si, s in enumerate(d['skills']):
                if di == domain_idx and si == skill_idx:
                    continue
                for ai, a in enumerate(s['actions']):
                    a_text = a.get('text', '').lower()
                    a_words = set(re.findall(r'\w+', a_text)) - stop_words
                    common = words & a_words
                    if len(common) >= 2:
                        related.append({
                            "domain_name": d['name'],
                            "skill_name": s['name'],
                            "action": a_text[:60] + "..." if len(a_text) > 60 else a_text,
                            "url": f"/action/{di}/{si}/{ai}"
                        })
                        if len(related) >= 5:
                            break
                if len(related) >= 5:
                    break
    except Exception as e:
        print(f"Ошибка поиска связанных навыков: {e}")
    return related

# РЕГИСТРАЦИЯ ФИЛЬТРОВ JINJA2
app.jinja_env.filters['slugify'] = slugify

@app.template_filter('domain_icon')
def domain_icon_filter(domain_name, index):
    return get_domain_icon(domain_name, index)

@app.template_filter('skill_icon')
def skill_icon_filter(skill_name, index):
    return get_skill_icon(skill_name, index)

@app.template_filter('domain_color')
def domain_color_filter(domain_name):
    return get_domain_color(domain_name)

@app.template_filter('skill_color')
def skill_color_filter(skill_name, domain_color, index):
    return get_skill_color(skill_name, domain_color, index)

@app.context_processor
def inject_globals():
    domains = (get_matrix() or {}).get("domains", [])
    sidebar_domains = []
    for i, d in enumerate(domains):
        domain_color = get_domain_color(d.get("name", ""))
        skills_list = []
        for si, s in enumerate(d.get("skills", [])):
            actions = s.get("actions", [])
            skills_list.append({
                "name": s.get("name", ""),
                "index": si,
                "color": get_skill_color(s.get("name", ""), domain_color, si),
                "icon": get_skill_icon(s.get("name", ""), si),
                "actions_count": len(actions),
            })
        sidebar_domains.append({
            "name": d.get("name", ""),
            "index": i,
            "color": domain_color,
            "icon": get_domain_icon(d.get("name", ""), i),
            "skills_count": len(skills_list),
            "skills": skills_list,
        })
    return {
        'ui_config': get_meta().get('ui_config', {}),
        'sidebar_domains': sidebar_domains,
        'get_domain_icon': get_domain_icon,
        'get_skill_icon': get_skill_icon,
        'get_domain_color': get_domain_color,
        'get_skill_color': get_skill_color
    }

# ----- ОСНОВНЫЕ МАРШРУТЫ -----

@app.route('/')
def index():
    """Стартовая страница — дашборд."""
    matrix = get_matrix() or {}
    domains = matrix.get("domains") or []
    total_skills = sum(len(d.get("skills", [])) for d in domains)
    total_actions = 0
    for d in domains:
        for s in d.get("skills", []):
            total_actions += len(s.get("actions", []))
    return render_template('home.html', domains=domains, stats={
        "domains": len(domains),
        "skills": total_skills,
        "actions": total_actions,
    })


@app.route('/matrix')
def matrix_view():
    """Матрица — сетка карточек доменов."""
    return render_template('matrix.html', domains=get_matrix()['domains'])


@app.route('/domain/<int:domain_idx>')
def domain_view(domain_idx):
    """Вью домена: дерево элементов слева направо."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    if domain_idx < 0 or domain_idx >= len(domains):
        return render_template('404.html'), 404
    domain = domains[domain_idx]
    domain_color = get_domain_color(domain.get("name", ""))
    domain_icon = get_domain_icon(domain.get("name", ""), domain_idx)
    domain_data = {
        "index": domain_idx,
        "name": domain.get("name", ""),
        "color": domain_color,
        "icon": domain_icon,
        "skills": []
    }
    for si, s in enumerate(domain.get("skills", [])):
        skill_color = get_skill_color(s.get("name", ""), domain_color, si)
        skill_icon = get_skill_icon(s.get("name", ""), si)
        skill_data = {
            "index": si,
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "color": skill_color,
            "icon": skill_icon,
            "actions": []
        }
        for ai, a in enumerate(s.get("actions", [])):
            action_data = {
                "index": ai,
                "text": a.get("text", ""),
                "template_id": a.get("template_id"),
                "subactions": []
            }
            for subi, sub in enumerate(a.get("subactions", [])):
                action_data["subactions"].append({
                    "index": subi,
                    "text": sub.get("text", ""),
                    "leaf_path": f"{domain_idx}/{si}/{ai}/{subi}"
                })
            if not action_data["subactions"]:
                action_data["leaf_path"] = f"{domain_idx}/{si}/{ai}"
            skill_data["actions"].append(action_data)
        domain_data["skills"].append(skill_data)
    return render_template('domain_view.html', domain=domain_data, current_domain_index=domain_idx, focus_skill=False)


@app.route('/domain/<int:domain_idx>/skill/<int:skill_idx>')
def domain_skill_view(domain_idx, skill_idx):
    """Вью навыка: дерево элементов (зависимости от выбранного в сайдбаре)."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    if domain_idx < 0 or domain_idx >= len(domains):
        return render_template('404.html'), 404
    domain = domains[domain_idx]
    skills = domain.get("skills", [])
    if skill_idx < 0 or skill_idx >= len(skills):
        return render_template('404.html'), 404
    skill = skills[skill_idx]
    domain_color = get_domain_color(domain.get("name", ""))
    domain_icon = get_domain_icon(domain.get("name", ""), domain_idx)
    skill_color = get_skill_color(skill.get("name", ""), domain_color, skill_idx)
    skill_icon = get_skill_icon(skill.get("name", ""), skill_idx)
    domain_data = {
        "index": domain_idx,
        "name": domain.get("name", ""),
        "color": domain_color,
        "icon": domain_icon,
        "skills": [{
            "index": skill_idx,
            "name": skill.get("name", ""),
            "description": skill.get("description", ""),
            "color": skill_color,
            "icon": skill_icon,
            "actions": []
        }]
    }
    for ai, a in enumerate(skill.get("actions", [])):
        action_data = {
            "index": ai,
            "text": a.get("text", ""),
            "template_id": a.get("template_id"),
            "subactions": []
        }
        for subi, sub in enumerate(a.get("subactions", [])):
            action_data["subactions"].append({
                "index": subi,
                "text": sub.get("text", ""),
                "leaf_path": f"{domain_idx}/{skill_idx}/{ai}/{subi}"
            })
        if not action_data["subactions"]:
            action_data["leaf_path"] = f"{domain_idx}/{skill_idx}/{ai}"
        domain_data["skills"][0]["actions"].append(action_data)
    return render_template('domain_view.html', domain=domain_data, current_domain_index=domain_idx, current_skill_index=skill_idx, focus_skill=True)


@app.route('/api/matrix')
def api_matrix():
    return jsonify(get_matrix())

@app.route('/api/tree')
def api_tree():
    """Дерево матрицы (корень → листья), уровни определяются автоматически."""
    return jsonify(get_tree())

def _leaf_breadcrumb(tree_nodes, path: list) -> str:
    """Строка «Домен → Навык → Действие» для листа по path."""
    if not path:
        return ""
    parts = []
    nodes = tree_nodes
    for i, idx in enumerate(path):
        idx = int(idx)
        if idx < 0 or idx >= len(nodes):
            break
        node = nodes[idx]
        parts.append(node.get("name", ""))
        if i + 1 < len(path) and node.get("children"):
            nodes = node["children"]
    return " → ".join(p for p in parts if p)


@app.route('/api/leaves')
def api_leaves():
    """Список всех листьев с path, template_id, url и иерархией (домен → навык → дерево)."""
    tree = get_tree()
    hierarchy = request.args.get("hierarchy", "").lower() in ("1", "true", "yes")
    leaves = collect_leaves(tree)
    out = []
    for n in leaves:
        p = n.get("path", [])
        item = {
            "path": p,
            "name": n.get("name"),
            "url": path_to_url(p),
            "template_id": n.get("template_id"),
        }
        if hierarchy:
            item["breadcrumb"] = _leaf_breadcrumb(tree, p)
        out.append(item)
    return jsonify(out)

@app.route('/api/meta')
def api_meta():
    return jsonify(get_meta())

@app.route('/graph')
def graph():
    return render_template('graph.html')

@app.route('/api/graph-data')
def graph_data():
    data = get_matrix()
    nodes = [{"id": "root", "name": "Middle Data Engineer", "type": "root", "level": 0}]
    links = []
    
    for di, d in enumerate(data['domains']):
        domain_color = get_domain_color(d['name'])
        domain_icon = get_domain_icon(d['name'], di)
        did = f"d{di}"
        nodes.append({
            "id": did,
            "name": d['name'],
            "type": "domain",
            "level": 1,
            "color": domain_color,
            "icon": domain_icon
        })
        links.append({"source": "root", "target": did})
        
        for si, s in enumerate(d['skills']):
            skill_color = get_skill_color(s['name'], domain_color, si)
            skill_icon = get_skill_icon(s['name'], si)
            sid = f"d{di}s{si}"
            nodes.append({
                "id": sid,
                "name": s['name'],
                "type": "skill",
                "level": 2,
                "domain_idx": di,
                "skill_idx": si,
                "color": skill_color,
                "icon": skill_icon,
                "description": s.get('description', '')
            })
            links.append({"source": did, "target": sid})
            
            for ai, a in enumerate(s['actions']):
                aid = f"d{di}s{si}a{ai}"
                leaf_path = f"{di}/{si}/{ai}"
                nodes.append({
                    "id": aid,
                    "name": a['text'],
                    "full_name": a['text'],
                    "type": "action",
                    "level": 3,
                    "domain_idx": di,
                    "skill_idx": si,
                    "action_idx": ai,
                    "leaf_path": leaf_path if 'subactions' not in a else None,
                })
                links.append({"source": sid, "target": aid})
                
                if 'subactions' in a:
                    for sub_idx, sub in enumerate(a['subactions']):
                        subid = f"d{di}s{si}a{ai}sub{sub_idx}"
                        nodes.append({
                            "id": subid,
                            "name": sub['text'],
                            "full_name": sub['text'],
                            "type": "subaction",
                            "level": 4,
                            "domain_idx": di,
                            "skill_idx": si,
                            "action_idx": ai,
                            "sub_idx": sub_idx,
                            "leaf_path": f"{di}/{si}/{ai}/{sub_idx}",
                        })
                        links.append({"source": aid, "target": subid, "label": "содержит"})
    
    return jsonify({"nodes": nodes, "links": links})

# ----- Универсальный маршрут листа (произвольная глубина) -----

@app.route('/leaf/<path:path>')
def leaf_page(path):
    """Страница листа по path (например 0/1/2 или 0/1/2/0)."""
    resolved = resolve_leaf_by_path(path)
    if not resolved:
        abort(404)
    domain, skill, action, parent_action_text = resolved
    path_parts = path.strip("/").split("/")
    di = int(path_parts[0]) if len(path_parts) > 0 else 0
    si = int(path_parts[1]) if len(path_parts) > 1 else 0
    ai = int(path_parts[2]) if len(path_parts) > 2 else 0
    sub_idx = int(path_parts[3]) if len(path_parts) > 3 else None
    domain_color = get_domain_color(domain["name"])
    skill_color = get_skill_color(skill["name"], domain_color, si)
    ctx = {
        "domain": domain,
        "skill": skill,
        "action": action,
        "action_text": action["text"],
        "di": di, "si": si, "ai": ai,
        "domain_color": domain_color,
        "skill_color": skill_color,
        "domain_icon": get_domain_icon(domain["name"], di),
        "skill_icon": get_skill_icon(skill["name"], si),
        "leaf_path": path,
    }
    if sub_idx is not None:
        ctx["sub_idx"] = sub_idx
        ctx["parent_action_text"] = parent_action_text
    return render_template("action_detail.html", **ctx)

@app.route('/api/leaf/<path:path>')
def leaf_api(path):
    """API листа: те же данные, что /api/action или /api/subaction."""
    resolved = resolve_leaf_by_path(path)
    if not resolved:
        return jsonify({"error": "Not found"}), 404
    domain, skill, action, parent_action_text = resolved
    meta = get_meta()
    template_id = action.get("template_id")
    template = meta.get("action_templates", {}).get(template_id or "", {})
    if template.get("is_parent"):
        return jsonify({"error": "Node is not a leaf"}), 400
    enriched = enrich_action(action, template, meta)
    description = build_description(action, template, domain, skill, meta)
    path_parts = [int(x) for x in path.strip("/").split("/") if x.strip()]
    related = find_related_skills_by_path(path_parts) if len(path_parts) >= 3 else []
    return jsonify({
        "title": action["text"],
        "description": description,
        "examples": enriched["examples"],
        "tools": enriched["tools"],
        "stack_labels": enriched["stack_labels"],
        "literature": enriched["literature"],
        "related_skills": related,
        "domain_color": get_domain_color(domain["name"]),
        "skill_color": get_skill_color(skill["name"], get_domain_color(domain["name"]), path_parts[1] if len(path_parts) > 1 else 0),
        "domain_icon": get_domain_icon(domain["name"], path_parts[0] if path_parts else 0),
        "skill_icon": get_skill_icon(skill["name"], path_parts[1] if len(path_parts) > 1 else 0),
        "leaf_path": path,
    })

def find_related_skills_by_path(path_parts):
    """По path листа возвращает связанные навыки (делегирует find_related_skills по di, si, ai)."""
    data = get_matrix()
    if "domains" not in data or len(path_parts) < 3:
        return []
    return find_related_skills(data, path_parts[0], path_parts[1], path_parts[2])

# ----- МАРШРУТЫ ДЛЯ ДЕЙСТВИЙ (обратная совместимость) -----

@app.route('/action/<int:di>/<int:si>/<int:ai>')
def action_page(di, si, ai):
    data = get_matrix()
    meta = get_meta()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        return render_template('action_detail.html',
                             domain=domain,
                             skill=skill,
                             action=action,
                             action_text=action['text'],
                             di=di, si=si, ai=ai,
                             domain_color=domain_color,
                             skill_color=skill_color,
                             domain_icon=get_domain_icon(domain['name'], di),
                             skill_icon=get_skill_icon(skill['name'], si))
    except (IndexError, KeyError) as e:
        print(f"Ошибка при загрузке действия: {e}")
        abort(404)

@app.route('/api/action/<int:di>/<int:si>/<int:ai>')
def action_api(di, si, ai):
    data = get_matrix()
    meta = get_meta()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        template_id = action.get('template_id')
        template = meta['action_templates'].get(template_id, {})
        
        # Если это родительский элемент, возвращаем информацию о поддействиях
        if template.get('is_parent', False):
            subactions_data = []
            if 'subactions' in action:
                for sub_idx, sub in enumerate(action['subactions']):
                    sub_template = meta['action_templates'].get(sub['template_id'], {})
                    subactions_data.append({
                        "text": sub['text'],
                        "template_id": sub['template_id'],
                        "name": sub_template.get('name', ''),
                        "url": f"/subaction/{di}/{si}/{ai}/{sub_idx}"
                    })
            
            domain_color = get_domain_color(domain['name'])
            skill_color = get_skill_color(skill['name'], domain_color, si)
            
            return jsonify({
                "title": action['text'],
                "description": "<p>Это группа компетенций. Выберите конкретный навык из списка ниже:</p>",
                "is_parent": True,
                "subactions": subactions_data,
                "domain_color": domain_color,
                "skill_color": skill_color,
                "domain_icon": get_domain_icon(domain['name'], di),
                "skill_icon": get_skill_icon(skill['name'], si)
            })
        
        enriched = enrich_action(action, template, meta)
        description = build_description(action, template, domain, skill, meta)
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        result = {
            "title": action['text'],
            "description": description,
            "examples": enriched['examples'],
            "tools": enriched['tools'],
            "stack_labels": enriched['stack_labels'],
            "literature": enriched['literature'],
            "related_skills": find_related_skills(data, di, si, ai),
            "domain_color": domain_color,
            "skill_color": skill_color,
            "domain_icon": get_domain_icon(domain['name'], di),
            "skill_icon": get_skill_icon(skill['name'], si)
        }
        
        return jsonify(result)
    except (IndexError, KeyError) as e:
        print(f"Ошибка API: {e}")
        return jsonify({"error": "Not found"}), 404

# ----- МАРШРУТЫ ДЛЯ ПОДДЕЙСТВИЙ -----

@app.route('/subaction/<int:di>/<int:si>/<int:ai>/<int:sub_idx>')
def subaction_page(di, si, ai, sub_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        
        if 'subactions' not in action or sub_idx >= len(action['subactions']):
            abort(404)
            
        sub = action['subactions'][sub_idx]
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        return render_template('action_detail.html',
                             domain=domain,
                             skill=skill,
                             action=sub,
                             action_text=sub['text'],
                             di=di, si=si, ai=ai, sub_idx=sub_idx,
                             parent_action_text=action['text'],
                             domain_color=domain_color,
                             skill_color=skill_color,
                             domain_icon=get_domain_icon(domain['name'], di),
                             skill_icon=get_skill_icon(skill['name'], si))
    except (IndexError, KeyError) as e:
        print(f"Ошибка при загрузке поддействия: {e}")
        abort(404)

@app.route('/api/subaction/<int:di>/<int:si>/<int:ai>/<int:sub_idx>')
def subaction_api(di, si, ai, sub_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        domain = data['domains'][di]
        skill = domain['skills'][si]
        action = skill['actions'][ai]
        
        if 'subactions' not in action or sub_idx >= len(action['subactions']):
            return jsonify({"error": "Subaction not found"}), 404
            
        sub = action['subactions'][sub_idx]
        template_id = sub.get('template_id')
        template = meta['action_templates'].get(template_id, {})
        
        if template.get('is_parent', False):
            return jsonify({"error": "Cannot view parent template directly"}), 400
        
        enriched = enrich_action(sub, template, meta)
        description = build_description(sub, template, domain, skill, meta)
        domain_color = get_domain_color(domain['name'])
        skill_color = get_skill_color(skill['name'], domain_color, si)
        
        result = {
            "title": sub['text'],
            "description": description,
            "examples": enriched['examples'],
            "tools": enriched['tools'],
            "stack_labels": enriched['stack_labels'],
            "literature": enriched['literature'],
            "domain_color": domain_color,
            "skill_color": skill_color,
            "domain_icon": get_domain_icon(domain['name'], di),
            "skill_icon": get_skill_icon(skill['name'], si),
            "parent_action": action['text']
        }
        
        return jsonify(result)
    except (IndexError, KeyError) as e:
        print(f"Ошибка API поддействия: {e}")
        return jsonify({"error": "Not found"}), 404

# ----- МАРШРУТЫ ДЛЯ ГРАФОВ ДОМЕНОВ -----

@app.route('/domain-graph/<int:domain_idx>')
def domain_graph(domain_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        if domain_idx >= len(data["domains"]):
            abort(404)
        domain = data["domains"][domain_idx]
        return render_template('domain_graph.html',
                             domain=domain,
                             domain_idx=domain_idx,
                             current_domain_index=domain_idx,
                             ui_config=meta.get('ui_config', {}))
    except (IndexError, KeyError, TypeError) as e:
        print(f"Ошибка при загрузке графа домена: {e}")
        abort(404)

@app.route('/api/domain-graph/<int:domain_idx>')
def domain_graph_data(domain_idx):
    data = get_matrix()
    meta = get_meta()
    try:
        if domain_idx >= len(data["domains"]):
            return jsonify({"error": "Domain not found"}), 404
        
        domain = data["domains"][domain_idx]
        nodes = []
        links = []
        
        domain_color = get_domain_color(domain['name'])
        domain_icon = get_domain_icon(domain['name'], domain_idx)
        domain_root_id = f"dg_root_{domain_idx}"
        
        nodes.append({
            "id": domain_root_id,
            "name": domain["name"],
            "type": "domain_root",
            "color": domain_color,
            "icon": domain_icon,
            "level": 0,
            "description": f"Домен: {domain['name']}"
        })
        
        for skill_idx, skill in enumerate(domain["skills"]):
            skill_id = f"dg_skill_{domain_idx}_{skill_idx}"
            skill_color = get_skill_color(skill['name'], domain_color, skill_idx)
            skill_icon = get_skill_icon(skill['name'], skill_idx)
            
            nodes.append({
                "id": skill_id,
                "name": skill["name"],
                "type": "skill",
                "icon": skill_icon,
                "color": skill_color,
                "level": 1,
                "description": skill.get("description", ""),
                "domain_idx": domain_idx,
                "skill_idx": skill_idx
            })
            links.append({"source": domain_root_id, "target": skill_id, "label": "содержит"})
            
            for action_idx, action in enumerate(skill["actions"]):
                action_id = f"dg_action_{domain_idx}_{skill_idx}_{action_idx}"
                template_id = action.get('template_id')
                template = meta['action_templates'].get(template_id, {})
                enriched = enrich_action(action, template, meta)
                stack_labels = enriched['stack_labels']
                
                action_leaf_path = f"{domain_idx}/{skill_idx}/{action_idx}" if 'subactions' not in action else None
                nodes.append({
                    "id": action_id,
                    "name": action['text'],
                    "full_name": action['text'],
                    "type": "action",
                    "level": 2,
                    "domain_idx": domain_idx,
                    "skill_idx": skill_idx,
                    "action_idx": action_idx,
                    "stack": stack_labels,
                    "color": "#f39c12",
                    "leaf_path": action_leaf_path,
                })
                links.append({"source": skill_id, "target": action_id, "label": "выполняет"})
                
                if 'subactions' in action:
                    for sub_idx, sub in enumerate(action['subactions']):
                        sub_id = f"dg_sub_{domain_idx}_{skill_idx}_{action_idx}_{sub_idx}"
                        nodes.append({
                            "id": sub_id,
                            "name": sub['text'],
                            "full_name": sub['text'],
                            "type": "subaction",
                            "level": 3,
                            "domain_idx": domain_idx,
                            "skill_idx": skill_idx,
                            "action_idx": action_idx,
                            "sub_idx": sub_idx,
                            "color": "#f39c12",
                            "leaf_path": f"{domain_idx}/{skill_idx}/{action_idx}/{sub_idx}",
                        })
                        links.append({"source": action_id, "target": sub_id, "label": "содержит"})
                
                if stack_labels:
                    for stack_idx, stack in enumerate(stack_labels):
                        stack_id = f"dg_stack_{domain_idx}_{skill_idx}_{action_idx}_{stack_idx}"
                        if not any(node["id"] == stack_id for node in nodes):
                            nodes.append({
                                "id": stack_id,
                                "name": stack.get("name", stack.get("key", "Technology")),
                                "type": "stack",
                                "icon": stack.get("icon", "cube"),
                                "color": stack.get("color", "#9b59b6"),
                                "level": 4,
                                "description": stack.get("description", "")
                            })
                        links.append({"source": action_id, "target": stack_id, "label": "использует"})
        
        return jsonify({
            "domain": {"name": domain["name"], "color": domain_color, "icon": domain_icon},
            "nodes": nodes,
            "links": links
        })
    except Exception as e:
        print(f"Ошибка при создании графа домена: {e}")
        return jsonify({"error": str(e)}), 500

# ----- МАРШРУТ ДЛЯ ЭКСПОРТА -----

@app.route('/export')
def export():
    return render_template('export.html')

# ----- СХЕМА И ВАЛИДАЦИЯ -----

@app.route('/api/schema')
def api_schema():
    """Информация о схеме источника (для догрузки и валидации)."""
    return jsonify({"ok": True, **get_schema_info()})


@app.route('/api/validate', methods=["POST"])
def api_validate():
    """Валидация структуры источника. Body: {domains: [...], action_templates: {...}, ...}."""
    data = request.get_json() or {}
    vr = validate_source(data)
    return jsonify({"ok": vr.ok, **vr.to_dict()})


# ----- НАСТРОЙКИ: бэкапы и восстановление -----

@app.route('/import')
def import_page():
    """Импорт данных — догрузка JSON/Excel."""
    return render_template('import.html')


@app.route('/settings')
def settings_page():
    return render_template('settings.html')


# ----- ЛИТЕРАТУРА: каталог, привязка к листам -----

@app.route('/literature')
def literature_page():
    return render_template('literature.html')

@app.route('/api/literature')
def api_literature_list():
    """Список литературы с привязкой к компетенциям (листам)."""
    meta = get_meta()
    lit = meta.get('literature', {})
    templates = meta.get('action_templates', {})
    template_to_lit = {}
    for tid, t in templates.items():
        for rid in t.get('resource_ids', []):
            template_to_lit.setdefault(rid, []).append({"template_id": tid, "name": t.get('name', tid)})
    out = []
    for rid, item in lit.items():
        out.append({
            "id": rid,
            "title": item.get("title", rid),
            "chapter": item.get("chapter", ""),
            "pages": item.get("pages", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "local_path": item.get("local_path") or item.get("file_path", ""),
            "linked_templates": template_to_lit.get(rid, []),
        })
    return jsonify(out)

@app.route('/api/literature', methods=['POST'])
def api_literature_add():
    """Ручное добавление литературы."""
    global _meta
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    meta = get_meta()
    lit = meta.setdefault('literature', {})
    lid = slugify(title)[:40] + '_' + hashlib.md5(title.encode()).hexdigest()[:6]
    if lid in lit:
        return jsonify({"error": "already exists", "id": lid}), 409
    lit[lid] = {
        "title": title,
        "chapter": (data.get('chapter') or '').strip(),
        "pages": (data.get('pages') or '').strip(),
        "url": (data.get('url') or '').strip(),
        "description": (data.get('description') or '').strip(),
    }
    save_meta(meta)
    return jsonify({"id": lid, "title": title})


@app.route('/api/literature/upload', methods=['POST'])
def api_literature_upload():
    """Загрузка физического файла (PDF и т.д.) в data/library с созданием записи литературы."""
    global _meta
    if "file" not in request.files:
        return jsonify({"error": "файл не выбран"}), 400
    f = request.files["file"]
    if f.filename == "" or not f.filename:
        return jsonify({"error": "файл не выбран"}), 400
    title = (request.form.get("title") or "").strip() or PathLib(f.filename).stem
    chapter = (request.form.get("chapter") or "").strip()
    pages = (request.form.get("pages") or "").strip()
    description = (request.form.get("description") or "").strip()
    lib_dir = _literature_dir()
    orig = PathLib(f.filename)
    suffix = (orig.suffix.lower() or ".pdf")
    if not suffix.startswith("."):
        suffix = "." + suffix
    stem = re.sub(r"[^\w\-]", "_", orig.stem)[:60]
    filepath = os.path.join(lib_dir, stem + suffix)
    n = 0
    while os.path.exists(filepath):
        n += 1
        filepath = os.path.join(lib_dir, f"{stem}_{n}{suffix}")
    try:
        f.save(filepath)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    rel_path = os.path.relpath(filepath, BASE_DIR)
    meta = get_meta()
    lit = meta.setdefault("literature", {})
    lid = slugify(title)[:40] + "_" + hashlib.md5((title + rel_path).encode()).hexdigest()[:6]
    if lid in lit:
        lid = lid + "_" + hashlib.md5(rel_path.encode()).hexdigest()[:4]
    lit[lid] = {
        "title": title,
        "chapter": chapter,
        "pages": pages,
        "url": "",
        "description": description,
        "local_path": rel_path,
    }
    save_meta(meta)
    return jsonify({"id": lid, "title": title, "local_path": rel_path})


@app.route('/api/literature/<lit_id>/link', methods=['POST'])
def api_literature_link(lit_id):
    """Привязка литературы к листам (по path). Добавляет lit_id в resource_ids шаблонов этих листов."""
    global _meta
    data = request.get_json() or {}
    leaf_paths = data.get('leaf_paths') or []
    if not leaf_paths:
        return jsonify({"error": "leaf_paths required"}), 400
    meta = get_meta()
    if lit_id not in meta.get('literature', {}):
        return jsonify({"error": "literature not found"}), 404
    templates = meta.setdefault('action_templates', {})
    tree = get_tree()
    updated = 0
    for path_str in leaf_paths:
        try:
            path = [int(x) for x in str(path_str).strip("/").split("/") if x.strip()]
        except ValueError:
            continue
        node = get_node_by_path(tree, path)
        if not node or node.get('children'):
            continue
        tid = node.get('template_id')
        if not tid or tid not in templates:
            continue
        rids = templates[tid].setdefault('resource_ids', [])
        if lit_id not in rids:
            rids.append(lit_id)
            updated += 1
    save_meta(meta)
    return jsonify({"updated": updated})


# Типы контента, которые считаем файлами для скачивания (не веб-страницы)
_DOWNLOADABLE_CONTENT_TYPES = (
    'application/pdf', 'application/octet-stream', 'application/x-pdf',
    'application/msword', 'application/vnd.openxmlformats-officedocument.',
    'application/zip', 'application/x-rar', 'application/epub+zip',
    'image/', 'audio/', 'video/', 'text/csv', 'text/plain',
)


def _is_downloadable_content_type(ct):
    """Проверяет, является ли Content-Type скачиваемым файлом (не веб-страница)."""
    if not ct:
        return False
    ct_lower = ct.lower().split(';')[0].strip()
    if ct_lower.startswith(('text/html', 'application/xhtml', 'text/xml')):
        return False
    for prefix in _DOWNLOADABLE_CONTENT_TYPES:
        if ct_lower.startswith(prefix):
            return True
    return False


@app.route('/api/literature/<lit_id>/download', methods=['POST'])
def api_literature_download(lit_id):
    """Скачивает файл по URL в каталог data/library и проставляет local_path у записи литературы."""
    import urllib.request
    import urllib.parse
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    meta = get_meta()
    if lit_id not in meta.get('literature', {}):
        return jsonify({"error": "literature not found"}), 404
    lib_dir = _literature_dir()
    try:
        import ssl
        cfg = load_app_config()
        ssl_verify = cfg.get("ssl_verify", True)
        if os.environ.get("DE_MATRIX_SSL_VERIFY", "").lower() in ("0", "false", "no"):
            ssl_verify = False
        ssl_ca_bundle = cfg.get("ssl_ca_bundle") or os.environ.get("DE_MATRIX_SSL_CA_BUNDLE")

        if not ssl_verify:
            ctx = ssl._create_unverified_context()
        elif ssl_ca_bundle and os.path.isfile(ssl_ca_bundle):
            ctx = ssl.create_default_context(cafile=ssl_ca_bundle)
        else:
            # Системные сертификаты (включая корпоративные CA в корпоративных сетях)
            ctx = ssl.create_default_context()

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if not _is_downloadable_content_type(content_type):
                resp.read()  # consume and close
                return jsonify({
                    "error": "Файлов для скачивания не найдено. Ссылка ведёт на веб-страницу.",
                    "preview_url": url,
                }), 400
            content = resp.read()
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".pdf"
        safe_id = re.sub(r'[^\w\-]', '_', lit_id)[:50]
        filename = f"{safe_id}{ext}"
        filepath = os.path.join(lib_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(content)
        rel_path = os.path.relpath(filepath, BASE_DIR)
        meta['literature'][lit_id]['local_path'] = rel_path
        save_meta(meta)
        return jsonify({"local_path": rel_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/domains')
def api_domains():
    """Структура доменов и навыков для выбора целевой ветки при догрузке."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    out = [{"name": d.get("name", ""), "skills": [s.get("name", "") for s in d.get("skills", [])]} for d in domains]
    return jsonify({"ok": True, "domains": out})


@app.route('/api/domain/<int:domain_idx>')
def api_domain(domain_idx):
    """Полные данные домена для вью дерева (слева направо)."""
    matrix = get_matrix()
    domains = (matrix or {}).get("domains") or []
    if domain_idx < 0 or domain_idx >= len(domains):
        return jsonify({"ok": False, "error": "Domain not found"}), 404
    d = domains[domain_idx]
    domain_color = get_domain_color(d.get("name", ""))
    domain_icon = get_domain_icon(d.get("name", ""), domain_idx)
    out = {
        "ok": True,
        "domain": {
            "index": domain_idx,
            "name": d.get("name", ""),
            "color": domain_color,
            "icon": domain_icon,
            "skills": []
        }
    }
    for si, s in enumerate(d.get("skills", [])):
        skill_color = get_skill_color(s.get("name", ""), domain_color, si)
        skill_icon = get_skill_icon(s.get("name", ""), si)
        skill_data = {
            "index": si,
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "color": skill_color,
            "icon": skill_icon,
            "actions": []
        }
        for ai, a in enumerate(s.get("actions", [])):
            action_data = {
                "index": ai,
                "text": a.get("text", ""),
                "template_id": a.get("template_id"),
                "subactions": []
            }
            for subi, sub in enumerate(a.get("subactions", [])):
                action_data["subactions"].append({
                    "index": subi,
                    "text": sub.get("text", ""),
                    "leaf_path": f"{domain_idx}/{si}/{ai}/{subi}"
                })
            if not action_data["subactions"]:
                action_data["leaf_path"] = f"{domain_idx}/{si}/{ai}"
            skill_data["actions"].append(action_data)
        out["domain"]["skills"].append(skill_data)
    return jsonify(out)


@app.route('/api/sources')
def api_sources():
    """Список файлов-источников в каталоге source_dir (JSON, YAML, Excel) для выбора при импорте."""
    files = _list_source_files()
    cfg = get_meta()
    checkpoint = load_checkpoint(PathLib(_checkpoint_path()))
    current = checkpoint.get("source_file") if checkpoint else None
    return jsonify({
        "source_dir": cfg.get("source_dir", "data/sources"),
        "files": files,
        "current": current,
    })


@app.route('/api/source/upload/preview', methods=["POST"])
def api_source_upload_preview():
    """Предпросмотр догрузки: парсинг файла без сохранения, возврат preview + validation."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Файл не передан"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Файл не выбран"}), 400
    ext = (os.path.splitext(f.filename)[1] or "").lower()
    if ext not in (".json", ".xlsx", ".xls"):
        return jsonify({"ok": False, "error": "Поддерживаются только JSON и Excel"}), 400

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        try:
            if ext == ".json":
                with open(tmp_path, "r", encoding="utf-8") as fp:
                    upload_data = json.load(fp)
            else:
                upload_data = load_excel(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "validation": {"ok": False, "errors": [str(e)]}}), 400

    from core.loaders import _normalize_unified
    from core.schema import validate_source
    upload_data = _normalize_unified(upload_data)
    vr = validate_source(upload_data)

    # Preview: плоская таблица для отображения
    preview_rows = []
    for d in upload_data.get("domains") or []:
        d_name = d.get("name") or ""
        for s in d.get("skills") or []:
            s_name = s.get("name") or ""
            for a in s.get("actions") or []:
                preview_rows.append({
                    "domain": d_name,
                    "skill": s_name,
                    "action": a.get("text") or "",
                    "subaction": "",
                    "template_id": a.get("template_id"),
                })
                for sub in a.get("subactions") or []:
                    preview_rows.append({
                        "domain": d_name,
                        "skill": s_name,
                        "action": a.get("text") or "",
                        "subaction": sub.get("text") or "",
                        "template_id": sub.get("template_id"),
                    })

    return jsonify({
        "ok": True,
        "preview": preview_rows,
        "validation": vr.to_dict(),
        "domains_count": len(upload_data.get("domains") or []),
    })


@app.route('/api/source/upload', methods=["POST"])
def api_source_upload():
    """Догрузка данных из JSON или Excel: слияние с текущим источником."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Файл не передан (ожидается поле 'file')"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Файл не выбран"}), 400
    ext = (os.path.splitext(f.filename)[1] or "").lower()
    if ext not in (".json", ".xlsx", ".xls"):
        return jsonify({"ok": False, "error": "Поддерживаются только JSON и Excel (.json, .xlsx, .xls)"}), 400

    merge_mode = (request.form.get("merge_mode") or "append").strip()
    target_domain = (request.form.get("target_domain") or "").strip() or None
    target_skill = (request.form.get("target_skill") or "").strip() or None
    if merge_mode not in ("append", "append_to_domain", "append_to_skill", "replace_domain", "replace_skill"):
        merge_mode = "append"
    if merge_mode == "append_to_domain" and not target_domain:
        return jsonify({"ok": False, "error": "Для режима «В домен» укажите target_domain"}), 400
    if merge_mode == "append_to_skill" and (not target_domain or not target_skill):
        return jsonify({"ok": False, "error": "Для режима «В навык» укажите target_domain и target_skill"}), 400

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        try:
            if ext == ".json":
                with open(tmp_path, "r", encoding="utf-8") as fp:
                    upload_data = json.load(fp)
            else:
                upload_data = load_excel(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as e:
        return jsonify({"ok": False, "error": f"Ошибка чтения файла: {e}"}), 400

    source_file = _current_source_for_backup()
    if not source_file:
        return jsonify({"ok": False, "error": "Нет текущего источника. Сначала загрузите источник через /api/source/load"}), 400

    source_dir = _source_dir_path()
    source_path = os.path.join(source_dir, source_file)
    if not os.path.isfile(source_path):
        return jsonify({"ok": False, "error": f"Файл источника не найден: {source_file}"}), 404

    # Бэкап перед догрузкой
    create_backup(
        PathLib(BASE_DIR),
        PathLib(BASE_DIR) / "config",
        PathLib(source_dir),
        source_file,
        _checkpoint_path(),
    )

    try:
        current = load_unified_source(source_path)
        merged = merge_upload_into_source(
            current, upload_data,
            merge_mode=merge_mode,
            target_domain=target_domain,
            target_skill=target_skill,
        )
        ext_src = os.path.splitext(source_path)[1].lower()
        if ext_src == ".json":
            with open(source_path, "w", encoding="utf-8") as fp:
                json.dump(merged, fp, ensure_ascii=False, indent=2)
        elif ext_src in (".yaml", ".yml"):
            import yaml
            with open(source_path, "w", encoding="utf-8") as fp:
                yaml.dump(merged, fp, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            return jsonify({"ok": False, "error": "Текущий источник не JSON/YAML, догрузка недоступна"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    _invalidate_caches()
    _ensure_data_loaded(force_source_filename=source_file)
    return jsonify({
        "ok": True,
        "message": "Данные догружены и объединены с источником",
        "source_file": source_file,
        "merge_mode": merge_mode,
    })


@app.route('/api/source/load', methods=["POST"])
def api_source_load():
    """Ручная подгрузка источника: перезагрузка из выбранного файла и перезапись чекпоинта."""
    data = request.get_json() or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "filename required"}), 400
    allowed = (".json", ".yaml", ".yml", ".xlsx", ".xls")
    if not any(filename.lower().endswith(ext) for ext in allowed):
        return jsonify({"ok": False, "error": "unsupported file type"}), 400
    if filename not in _list_source_files():
        return jsonify({"ok": False, "error": "file not found in source_dir"}), 404
    source_file = _current_source_for_backup()
    if source_file:
        create_backup(
            PathLib(BASE_DIR),
            PathLib(BASE_DIR) / "config",
            PathLib(_source_dir_path()),
            source_file,
            _checkpoint_path(),
        )
    _invalidate_caches()
    _ensure_data_loaded(force_source_filename=filename)
    return jsonify({"ok": True, "source_file": filename, "message": "Источник загружен, чекпоинт обновлён"})


@app.route('/api/backups')
def api_backups():
    """Список бэкапов конфига и источника."""
    backups = list_backups(PathLib(BASE_DIR))
    return jsonify({"ok": True, "backups": backups})


@app.route('/api/backups/<backup_id>/compatibility')
def api_backup_compatibility(backup_id):
    """Проверка совместимости бэкапа с текущей схемой."""
    compatible, warning = check_backup_compatibility(PathLib(BASE_DIR), backup_id)
    return jsonify({
        "ok": True,
        "backup_id": backup_id,
        "compatible": compatible,
        "warning": warning,
    })


@app.route('/api/restore', methods=["POST"])
def api_restore():
    """Восстановление из бэкапа: перезапись config и source, перезагрузка данных."""
    data = request.get_json() or {}
    backup_id = (data.get("backup_id") or data.get("id") or "").strip()
    force = bool(data.get("force"))
    if not backup_id:
        return jsonify({"ok": False, "error": "backup_id required"}), 400

    compatible, warning = check_backup_compatibility(PathLib(BASE_DIR), backup_id)
    if not compatible and not force:
        return jsonify({
            "ok": False,
            "error": "Несовместимость схемы",
            "warning": warning,
            "force_required": True,
        }), 409

    config_dir = PathLib(BASE_DIR) / "config"
    source_dir = PathLib(_source_dir_path())
    if not restore_backup(PathLib(BASE_DIR), config_dir, source_dir, backup_id):
        return jsonify({"ok": False, "error": "Backup not found or restore failed"}), 404
    invalidate_metadata_cache()
    _invalidate_caches()
    get_matrix()
    get_tree()
    return jsonify({
        "ok": True,
        "message": "Данные восстановлены из бэкапа, конфиг и источник обновлены",
        "backup_id": backup_id,
    })


@app.route('/api/reload')
def api_reload():
    """Перезагрузка: сброс кэша и повторная сверка источника с чекпоинтом (при изменении файла или для autoscale)."""
    source_file = _current_source_for_backup()
    if source_file:
        create_backup(
            PathLib(BASE_DIR),
            PathLib(BASE_DIR) / "config",
            PathLib(_source_dir_path()),
            source_file,
            _checkpoint_path(),
        )
    _invalidate_caches()
    get_matrix()
    get_tree()
    return jsonify({"ok": True, "message": "Кэш сброшен, данные загружены из источника/чекпоинта"})


# ----- ОТЛАДОЧНЫЕ МАРШРУТЫ -----

@app.route('/debug')
def debug():
    cfg = get_meta()
    checkpoint = load_checkpoint(PathLib(_checkpoint_path()))
    return jsonify({
        "source_dir": cfg.get("source_dir"),
        "checkpoint_file": cfg.get("checkpoint_file"),
        "current_source": checkpoint.get("source_file") if checkpoint else None,
        "literature_dir": cfg.get("literature_dir"),
        "config": "config/settings.yaml (пути); мета — из единого источника (файл в source_dir)",
        "matrix_keys": list(get_matrix().keys()),
        "meta_keys": [k for k in cfg.keys() if k not in ("source_dir", "checkpoint_file", "literature_dir", "flexible")],
    })

# ----- СТАТИЧЕСКИЕ ФАЙЛЫ И ОБРАБОТКА ОШИБОК -----

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Data Engineer Matrix')
    parser.add_argument('--port', type=int, default=5001, help='Port to run on (5000 on macOS often used by AirPlay)')
    parser.add_argument('--auto-port', action='store_true', help='Find free port automatically')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    os.makedirs('data', exist_ok=True)
    os.makedirs('data/sources', exist_ok=True)
    os.makedirs('data/backups', exist_ok=True)
    os.makedirs('config', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('templates', exist_ok=True)

    # Единый источник: data/sources/matrix.json (или другой файл из source_dir). Чекпоинт — data/checkpoint.yaml

    port = args.port
    if args.auto_port:
        port = find_free_port(args.port)
        if not port:
            print("❌ Не найдено свободных портов")
            sys.exit(1)

    debug_mode = args.debug or True
    print(f"\n🚀 Запуск на порту {port}")
    print(f"📊 Матрица: http://localhost:{port}")
    print(f"📈 Граф: http://localhost:{port}/graph")
    print(f"📋 Экспорт: http://localhost:{port}/export")
    print(f"🔧 Отладка: http://localhost:{port}/debug\n")

    app.run(debug=debug_mode, host='0.0.0.0', port=port)