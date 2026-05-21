#!/usr/bin/env python
"""Generate synthetic Repair Jobs for scale testing the cockpit's pagination
and kanban scroll. All seeded records carry a TEST-F-LOAD-<uuid> prefix on
their Customer names so they can be cleanly removed.

SAFETY: refuses to run unless BARO_ALLOW_SYNTHETIC=1 is set in the environment.
This prevents accidental seeding of real production sites.
"""
import argparse, os, sys, uuid, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from erpnext_client import get_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=100, help='Jobs to create')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--cleanup', action='store_true',
        help='Delete all TEST-F-LOAD-* records and exit')
    args = parser.parse_args()

    if os.environ.get('BARO_ALLOW_SYNTHETIC') != '1':
        print('Refusing to run. Set BARO_ALLOW_SYNTHETIC=1 in your env to enable.')
        sys.exit(2)

    client = get_client()
    if not args.execute:
        print('Use --execute to actually write.')
        sys.exit(1)

    def call(method, args_=None):
        return client._request('POST', f'/api/method/{method}',
                               payload=(args_ or {}))['message']

    if args.cleanup:
        _cleanup_all(client)
        return

    groups = call('frappe.client.get_list', {
        'doctype': 'Customer Group',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    territories = call('frappe.client.get_list', {
        'doctype': 'Territory',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    if not groups or not territories:
        print('No non-group Customer Group / Territory.')
        sys.exit(3)

    batch_id = uuid.uuid4().hex[:8]
    states = ['Texas', 'Florida', 'New York', 'New Jersey']
    equipment = ['Combi Oven', 'Walk-in Cooler', 'Ice Machine', 'Dishwasher',
                 'Fryer', 'Mixer', 'Espresso Machine']
    urgencies = ['Emergency', 'Today', 'This Week', 'Scheduled']

    print(f"Seeding {args.count} synthetic Repair Jobs (batch={batch_id})...")
    created = 0
    failed = 0
    for i in range(args.count):
        suffix4 = ''.join(random.choices('0123456789', k=4))
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_name': f"TEST-F-LOAD-{batch_id} #{i+1}",
                'caller_phone': '+1212' + str(500 + i % 500).zfill(3) + suffix4,
                'service_state': random.choice(states),
                'equipment_type': random.choice(equipment),
                'symptom': f"Synthetic symptom #{i+1}",
                'urgency': random.choice(urgencies),
            }})
            created += 1
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{args.count}")
        except Exception as e:
            failed += 1
            if failed > 5:
                print(f"  too many failures ({failed}), aborting: {e}")
                sys.exit(4)
    print(f"\nDone. Created {created}/{args.count} (failed {failed}).")


def _cleanup_all(client):
    print('Cleaning all TEST-F-LOAD-* records...')
    custs = client.list_docs('Customer',
        filters=[['name', 'like', 'TEST-F-LOAD-%']],
        fields=['name'], limit=5000)
    print(f"  {len(custs)} TEST-F-LOAD-* customers to clean")
    for cust in custs:
        rjs = client.list_docs('Repair Job',
            filters=[['customer', '=', cust['name']]],
            fields=['name'], limit=50)
        for rj in rjs:
            try: client._request('DELETE', f'/api/resource/Repair Job/{rj["name"]}')
            except Exception: pass
        for ent in ('Contact', 'Address'):
            try:
                ents = client.list_docs(ent,
                    filters=[
                        ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                        ['Dynamic Link', 'link_name', '=', cust['name']],
                    ], fields=['name'], limit=20)
            except Exception:
                ents = []
            for e in ents:
                try: client._request('DELETE', f'/api/resource/{ent}/{e["name"]}')
                except Exception: pass
        try: client._request('DELETE', f'/api/resource/Customer/{cust["name"]}')
        except Exception as e: print(f"  warn: Customer {cust['name']}: {e}")
    print('Done.')


if __name__ == '__main__':
    main()
