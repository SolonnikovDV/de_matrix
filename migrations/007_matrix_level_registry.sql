-- Реестр динамических таблиц уровней (имя таблицы = латинский идентификатор из matrix_levels + перевод/транслит).
-- Сами таблицы lvl* создаются приложением при replace; DROP выполняется перед пересозданием.

CREATE TABLE IF NOT EXISTS matrix_struct.matrix_level_registry (
    depth INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    sql_table VARCHAR(128) NOT NULL UNIQUE
);
