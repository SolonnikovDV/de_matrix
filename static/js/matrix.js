// Основные функции для матрицы
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM загружен, инициализация обработчиков...');
    
    // Инициализация обработчиков для матрицы, если мы на странице матрицы
    if (document.getElementById('matrix')) {
        initMatrixHandlers();
    }
    
    // Граф на странице /graph инициализируется в graph.html (своя логика модалов)
    // Не создаём MatrixGraph здесь — graph.html переопределяет класс и создаёт экземпляр
});

function initMatrixHandlers() {
    // Обработка кликов по доменам
    const domainCards = document.querySelectorAll('.domain-card');
    console.log('Найдено доменов:', domainCards.length);
    
    domainCards.forEach(card => {
        const header = card.querySelector('.domain-header');
        if (header) {
            header.removeEventListener('click', handleDomainClick);
            header.addEventListener('click', handleDomainClick);
        }
    });
    
    // Обработка кликов по навыкам
    const skillItems = document.querySelectorAll('.skill-item');
    console.log('Найдено навыков:', skillItems.length);
    
    skillItems.forEach(skill => {
        const header = skill.querySelector('.skill-header');
        if (header) {
            header.removeEventListener('click', handleSkillClick);
            header.addEventListener('click', handleSkillClick);
        }
    });
    
    // Обработка кликов по действиям
    const actionItems = document.querySelectorAll('.action-item');
    console.log('Найдено действий:', actionItems.length);
    
    actionItems.forEach(action => {
        action.removeEventListener('click', handleActionClick);
        action.addEventListener('click', handleActionClick);
        
        // Добавляем стиль курсора для указания кликабельности
        action.style.cursor = 'pointer';
    });
    
    // Открываем первый домен по умолчанию для примера
    if (domainCards.length > 0) {
        setTimeout(() => {
            domainCards[0].classList.add('expanded');
        }, 500);
    }
}

function handleDomainClick(e) {
    e.stopPropagation();
    const card = e.currentTarget.closest('.domain-card');
    if (card) {
        card.classList.toggle('expanded');
        
        // Закрываем все скиллы при закрытии домена
        if (!card.classList.contains('expanded')) {
            const skillItems = card.querySelectorAll('.skill-item');
            skillItems.forEach(skill => {
                skill.classList.remove('expanded');
            });
        }
    }
}

function handleSkillClick(e) {
    e.stopPropagation();
    const skill = e.currentTarget.closest('.skill-item');
    if (skill) {
        skill.classList.toggle('expanded');
    }
}

function handleActionClick(e) {
    e.stopPropagation();
    const action = e.currentTarget;
    const domainId = action.dataset.domainId;
    const skillId = action.dataset.skillId;
    const actionIdx = action.dataset.actionIdx;
    
    console.log('Клик по действию:', {domainId, skillId, actionIdx});
    
    if (domainId !== undefined && skillId !== undefined && actionIdx !== undefined) {
        // Переходим на детальную страницу действия
        window.location.href = `/action/${domainId}/${skillId}/${actionIdx}`;
    } else {
        console.error('Отсутствуют данные для перехода', {domainId, skillId, actionIdx});
    }
}

// MatrixGraph для общего графа определён в graph.html (с модалами).
// Заглушка для совместимости, если graph.html не загружен:
if (typeof window.MatrixGraph === 'undefined') {
    window.MatrixGraph = class MatrixGraph {
        constructor() { this.network = null; this.nodes = null; this.edges = null; }
        fit() { if (this.network) this.network.fit(); }
        center() { if (this.network) this.network.moveTo({ position: { x: 0, y: 0 }, scale: 1 }); }
        reset() { if (this.network) { this.network.setSelection([]); this.network.fit(); } }
    };
}

// Функция для создания slug из строки (для якорей)
function slugify(text) {
    if (!text) return '';
    return text.toString().toLowerCase()
        .replace(/\s+/g, '-')
        .replace(/[^\w\-]+/g, '')
        .replace(/\-\-+/g, '-')
        .replace(/^-+/, '')
        .replace(/-+$/, '');
}

// Делаем slugify доступным глобально (MatrixGraph уже в window из блока выше)
window.slugify = slugify;