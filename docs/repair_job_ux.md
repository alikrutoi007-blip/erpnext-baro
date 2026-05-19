# Repair Job UX Enhancements

Дата обновления: 2026-05-19

Цель: сделать `Repair Job` понятной рабочей карточкой для диспетчера, production team и менеджера. Это не отдельная CRM поверх ERPNext, а улучшенный UX вокруг центрального Baro DocType.

## Что изменено

### Form Layout

Форма `Repair Job` теперь разбита на понятные секции:

1. `Intake - Client, Status, Source`
2. `Call Intelligence - What happened on the call`
3. `Equipment and Problem`
4. `Money - Diagnostic, Estimate, Approval`
5. `Team - Owner, Technician, Client Work Group`
6. `Diagnosis and Parts`
7. `Repair, Payment, Warranty`
8. `Internal Notes and Call Evidence`

Длинные секции с AI/call/evidence/team detail сделаны collapsible, чтобы форма не выглядела перегруженной.

### Required Intake Fields

Обязательные поля для нормальной карточки:

- `status`
- `customer`
- `caller_phone`
- `area`
- `purpose_of_call`
- `service_summary`

Это минимальный набор, чтобы не потерять клиента и смысл заявки.

### List View and Filters

Усилены поля для list view и стандартных фильтров:

- `status`
- `customer`
- `caller_phone`
- `area`
- `service_summary`
- `equipment_type`
- `technician`
- `prepayment_status`
- `client_approval_status`
- `parts_status`
- `warranty_end_date`
- `call_datetime`

### Quick Buttons

Создан Client Script: `Baro Repair Job Form UX`.

На форме появляются быстрые действия:

- `Open Customer`
- `Open Contact`
- `Open Address`
- `Open Client Group`
- `Open Recording`
- `Create Follow-up ToDo`

### List Indicators

Создан Client Script: `Baro Repair Job List UX`.

List View получает цветовые индикаторы по `status`.

## Role Views

Созданы отдельные рабочие пространства:

- `Baro Dispatch Desk`
- `Baro Production Desk`
- `Baro Manager Desk`

Созданы kanban boards:

- `Baro Dispatch Board`
- `Baro Production Board`
- `Baro Manager Board`

Созданы number cards:

- `Baro Dispatch Queue`
- `Baro Production Queue`
- `Baro Estimate Approval Queue`
- `Baro Warranty Follow-up Queue`
- `Baro Paid Jobs`

## Commands

Dry-run:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\enhance_repair_job_experience.py
```

Execute:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\enhance_repair_job_experience.py --execute
```

Verify:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\verify_repair_job_experience.py
```

## Notes

- Google Sheets не затрагивался.
- Данные `Repair Job` не удалялись.
- `frappe.clear_cache` через REST не whitelisted, поэтому если UI сразу не обновился, сделай hard refresh браузера.
- Role desks можно открыть через `Ctrl+K` в ERPNext:
  - `Baro Dispatch Desk`
  - `Baro Production Desk`
  - `Baro Manager Desk`

