# Baro CRM Demo Environment

Дата обновления: 2026-05-18

Цель: дать руководству понятную демо-витрину ERPNext без зависимости от Google Sheets. В одном месте должны быть видны клиентские карточки, ремонтные заявки, статусы, канбан, задачи и логика handoff между ролями.

## Что создано в ERPNext

- Workspace: `Baro CRM Demo`
- Kanban Board: `Baro Repair Job Pipeline`
- Number Cards:
  - `Baro Open Repair Jobs`
  - `Baro Needs Follow-up`
  - `Baro Active Repairs`
- Demo Repair Jobs:
  - `RJ-2026-00002` - `DEMO - Sunrise Diner` - `Diagnostics Offered`
  - `RJ-2026-00003` - `DEMO - Gulf Coast Grill` - `Waiting Prepayment`
  - `RJ-2026-00004` - `DEMO - Harbor Sushi` - `Technician Assigned`
  - `RJ-2026-00005` - `DEMO - Brooklyn Coffee Lab` - `Estimate Sent`
  - `RJ-2026-00006` - `DEMO - Orlando Pizza Works` - `Parts Needed`
  - `RJ-2026-00007` - `DEMO - Houston BBQ House` - `Repair In Progress`
  - `RJ-2026-00008` - `DEMO - Sarasota Hotel Kitchen` - `Paid`
  - `RJ-2026-00009` - `DEMO - Vegas Buffet` - `Warranty Active`
- Demo Project: `PROJ-0002` / `DEMO - Marriott Residence Inn Client Work Group`
- Demo Tasks:
  - `DEMO - Confirm ETA and payment method`
  - `DEMO - Dispatch technician and update client`
  - `DEMO - Review diagnosis and prepare estimate`
  - `DEMO - Warranty follow-up after completion`
- Demo Employees:
  - `DEMO - Omar Technician`
  - `DEMO - Diego Technician`
  - `DEMO - Lena Dispatcher`
- Demo Service Items:
  - `DEMO-DIAGNOSTIC-SERVICE`
  - `DEMO-REPAIR-LABOR`
  - `DEMO-PARTS`
- Demo ToDos: 5 open follow-up tasks connected to `Repair Job`
- Demo Sales Invoice: `ACC-SINV-2026-00001` / Draft / `$520`

## Как открыть

1. Открой ERPNext: `http://100.127.172.110:8080`
2. В поиске сверху нажми `Ctrl+K`.
3. Найди `Baro CRM Demo`.
4. Открой workspace и покажи:
   - верхние number cards;
   - shortcut `Repair Pipeline`;
   - список `All Repair Jobs`;
   - карточку клиента из любой `DEMO - ...` заявки;
   - проект `DEMO - Marriott Residence Inn Client Work Group`;
   - связанные demo tasks.
   - service items and draft invoice.

Role-specific workspaces:

- `Baro Dispatch Desk` - для диспетчера
- `Baro Production Desk` - для production/техников
- `Baro Manager Desk` - для estimate/payment/warranty контроля

Прямая ссылка обычно выглядит так:

`http://100.127.172.110:8080/app/baro-crm-demo`

## Сценарий показа руководству

### 1. Главная мысль

ERPNext становится единым местом, где компания видит всю историю клиента:

`звонок -> клиент -> адрес -> оборудование -> диагностика -> техник -> estimate -> ремонт -> оплата -> гарантия`

### 2. Покажи workspace

Скажи:

> Это не просто таблица. Это рабочий центр: заявки, клиенты, задачи, статусы, деньги и гарантия в одной системе.

Покажи:

- сколько открытых repair jobs;
- сколько зависло на follow-up/prepayment/client approval;
- сколько сейчас активно в ремонте.

### 3. Покажи kanban

Открой `Repair Pipeline`.

Покажи, что каждая колонка соответствует стадии процесса:

- `Diagnostics Offered`
- `Waiting Prepayment`
- `Technician Assigned`
- `Estimate Sent`
- `Parts Needed`
- `Repair In Progress`
- `Paid`
- `Warranty Active`

Скажи:

> Сейчас мы видим не просто записи, а весь production pipeline. Руководитель сразу понимает, где деньги стоят, где клиент ждет, где техник занят, где гарантия.

### 4. Открой одну заявку

Лучший пример: `RJ-2026-00005` / `DEMO - Brooklyn Coffee Lab`.

Покажи поля:

- Customer
- Contact
- Service Address
- Caller Phone
- Area
- Marketing Source
- Equipment Type
- Purpose of Call
- AI Summary
- Internal Comment
- Status

Скажи:

> Это карточка как в поликлинике: вся история клиента, что сломалось, кто занимался, что обещали, какой следующий шаг.

### 5. Покажи project/tasks

Открой `DEMO - Marriott Residence Inn Client Work Group`.

Покажи, что вокруг лида можно автоматически создать рабочую группу:

- Confirm ETA/payment
- Dispatch technician
- Review diagnosis/estimate
- Warranty follow-up

Скажи:

> В будущем при новом qualified lead система сама создает рабочую группу и задачи для нужных людей. Это уменьшит хаос в чатах и риск забыть клиента.

### 6. Покажи людей и деньги

Открой `RJ-2026-00008` / `DEMO - Sarasota Hotel Kitchen`.

Покажи:

- technician: `DEMO - Omar Technician`
- diagnostic price: `$159`
- estimate amount: `$520`
- prepayment: `Paid`
- parts status: `Installed`
- warranty end date
- invoice: `ACC-SINV-2026-00001`

Скажи:

> Здесь видно, что CRM не заканчивается на звонке. Она соединяет клиента, техника, работу, сумму, оплату и гарантию.

## Команды

Dry-run:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\setup_demo_environment.py
```

Execute:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\setup_demo_environment.py --execute
```

Проверка:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\verify_mvp_setup.py
python .\scripts\verify_repair_job_experience.py
python .\scripts\verify_demo_environment.py
```

## Важно

- Demo records начинаются с `DEMO - ...`, чтобы их было легко отличить от реальных клиентов.
- Скрипт идемпотентный: повторный запуск обновляет демо-окружение и не должен создавать дубликаты по `DEMO-BARO-###`.
- Скрипт использует реальные ERPNext workflow actions, а не просто меняет поле `status`.
- Перед презентацией запускай `python .\scripts\verify_demo_environment.py`.
- Google Sheets сейчас не нужен для демонстрации этого окружения.
