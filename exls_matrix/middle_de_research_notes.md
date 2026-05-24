# Research notes: Middle Data Engineer (stack focus)

## Как сформировано понимание middle DE

- Базовый профиль: инженер, который уже самостоятельно ведет ETL/ELT задачи end-to-end, умеет проектировать модели хранения и объяснять trade-off по производительности/качеству данных.
- По стеку приоритета (Spark + Airflow + Greenplum/ClickHouse + Kafka + dbt): middle должен не только "знать инструменты", но и применять их в архитектурных решениях (инкрементальность, идемпотентность, SCD, partition/distribution, качество данных).
- Граница middle vs senior: middle решает большинство задач автономно в известном контексте; senior-level probe добавляет дизайн в условиях неопределенности, эволюцию схем, масштаб x10, и обоснование через метрики/планы выполнения.

## Приоритет: видео из плана

### 1) `https://youtu.be/0PfvY_1UDxM`
- Определено как мок-собеседование на middle DE (`rzv Data Engineering`, июнь 2024).
- Извлечены структура и фокус интервью: DWH, SQL, Python, live coding, разбор опыта.
- В практику перенесено: обязательные секции вопросов + практические задачи, а не только теория.

### 2) `https://youtu.be/NRWj8oEO3Ss`
- Определено как реальное интервью на DE с подробным разбором.
- Покрытие тем очень широкое и релевантное матрице: слои DWH, Data Vault/Anchor, SCD, Spark internals, SQL join/индексы, Python core, Kafka delivery semantics, Airflow.
- В практику перенесено: на каждый навык добавлен проверочный вопрос "на понимание механики", а также более сложный growth-вопрос.

### 3) `https://youtu.be/ZdmWjWIUn2A`
- Определено как мок-собеседование middle DE (`S1E3`, июль 2024).
- Покрытие: DWH+ML контур, стриминг/Kafka, SQL live coding, Python fundamentals.
- В практику перенесено: баланс теории и прикладной задачи с ограничениями по времени/данным.

### 4) `https://youtu.be/hTjo-QVWcK0`
- Извлечена транскрипция.
- Ключевые акценты: ежедневная эксплуатация пайплайнов, ETL/качество данных, оптимизация, взаимодействие с аналитиками/DS, важность Python+SQL+cloud+Spark.
- В практику перенесено: акцент на reliability и коммуникацию между доменами, а не только на код.

### 5) `https://youtu.be/GqW9mJdzoPQ`
- Стабильную транскрипцию через доступные инструменты получить не удалось (получена только заглушка страницы YouTube).
- Использовано как дополнительный сигнал по теме роста до senior, но без точечного цитирования содержимого.

## Дополнительные источники (актуальные практики)

- Spark SQL performance tuning: `https://spark.apache.org/docs/latest/sql-performance-tuning.html`
- Airflow best practices: `https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html`
- dbt best practices: `https://docs.getdbt.com/best-practices`
- dbt incremental models: `https://docs.getdbt.com/docs/build/incremental-models`
- dbt data tests: `https://docs.getdbt.com/docs/build/data-tests`
- Kafka delivery semantics: `https://docs.confluent.io/kafka/design/delivery-semantics.html`
- Greenplum partitioning/admin guide: `https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-greenplum/7/greenplum-database/admin_guide-ddl-ddl-partition.html`
- PostgreSQL partitioning: `https://www.postgresql.org/docs/current/ddl-partitioning.html`
- ClickHouse best practices: `https://clickhouse.com/docs/best-practices`
- Anchor modeling reference: `https://en.wikipedia.org/wiki/Anchor_modeling`
- Hiring expectations by level (recruiting perspective): `https://datatalks.club/podcast/hiring-for-data-engineering-jobs-in-europe.html`

## Вывод для текущей матрицы

- Для каждого навыка в `martrix_de_storage` должны одновременно присутствовать:
  - проверка понятийной глубины (как работает механизм),
  - проверка практической реализации (как спроектирует/реализует),
  - проверка зрелости (как поведет себя в edge-case и при росте нагрузки/сложности).
- Именно поэтому в заполнении матрицы добавлены:
  - вопросы уровня middle,
  - практические задания уровня middle+,
  - отдельные senior-growth probes в пределах того же навыка.
