#!/usr/bin/env python
"""F backend smoke. Calls create_repair_job + find_dedup_warnings against
the live ERPNext via the existing ERPNextClient. All test records get a
per-run TEST-F-* prefix on Customer names and are cleaned at the end.

Per the 2026-05-21 plan:
  - Unique generated test_phone per run (no fixed +12125559099)
  - --clean-stale sweeps TEST-F-* records older than 1 day before the run
    (default ON in --execute; disable with --no-clean-stale)
"""
import argparse, sys, uuid, random
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from erpnext_client import get_client, ERPNextError


def _resource_path(doctype, name):
    return f"/api/resource/{quote(doctype)}/{quote(name)}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true',
        help='Actually call create endpoints. Without this, only reads happen.')
    parser.add_argument('--keep', action='store_true', help='Skip post-run cleanup.')
    parser.add_argument('--clean-stale', dest='clean_stale', action='store_true', default=True,
        help='Before the run, delete TEST-F-* records older than 1 day. Default ON.')
    parser.add_argument('--no-clean-stale', dest='clean_stale', action='store_false',
        help='Skip the pre-run stale sweep.')
    parser.add_argument('--stale-hours', type=int, default=24,
        help='Hours threshold for stale TEST-F-* records (default 24).')
    args = parser.parse_args()

    client = get_client()
    if not args.execute and not client.config.dry_run:
        print('Refusing to run write tests without --execute or ERPNEXT_DRY_RUN=1.')
        sys.exit(1)

    # Pre-run stale sweep
    if args.clean_stale and args.execute:
        _clean_stale_test_records(client, hours=args.stale_hours)

    # Per-run prefix + unique phone
    run_id = f"TEST-F-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    test_phone_suffix = ''.join(random.choices('0123456789', k=4))
    test_phone = '+1212555' + test_phone_suffix
    print(f"Run prefix : {run_id}")
    print(f"Test phone : {test_phone}\n")

    def call(method, args_=None):
        # Frappe REST whitelisted-method body: args at top level (NOT wrapped)
        return client._request('POST', f'/api/method/{method}',
                               payload=(args_ or {}))['message']

    failures = []
    rj_name = []

    def check(name, fn):
        try:
            fn()
            print(f"  OK   {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL {name}: {e}")

    # T1: find_dedup_warnings shape
    def t1():
        r = call('baro_crm.api.repair_job.find_dedup_warnings',
                 {'caller_phone': test_phone})
        assert isinstance(r, dict)
        for key in ('phone_match_customer', 'phone_multi_match',
                    'name_match_customer', 'similar_customers', 'active_jobs'):
            assert key in r, f"missing key {key}"
    check('find_dedup_warnings shape', t1)

    # T2: create_repair_job minimal payload
    def t2():
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} Sunrise Diner",
            'caller_phone': test_phone,
            'service_state': 'New York',
            'equipment_type': 'Combi Oven',
            'symptom': 'Not heating',
            'urgency': 'Today',
        }})
        assert r['ok'] is True
        assert r['name'].startswith('RJ-')
        rj_name.append(r['name'])
    check('create_repair_job minimal payload', t2)

    # T3: active-RJ warning surfaces
    def t3():
        r = call('baro_crm.api.repair_job.find_dedup_warnings', {
            'caller_phone': test_phone,
            'equipment_type': 'Combi Oven',
        })
        assert any(j['name'] == rj_name[0] for j in r['active_jobs']), \
            f"expected RJ {rj_name[0]} in active_jobs, got {r['active_jobs']}"
    check('active-RJ warning fires', t3)

    # T4: incomplete address -> text + needs_review=1
    def t4():
        unique4 = ''.join(random.choices('0123456789', k=4))
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} Vague Address Test",
            'caller_phone': '+1212556' + unique4,
            'service_state': 'New York',
            'equipment_type': 'Ice Machine',
            'symptom': 'Stopped making ice',
            'urgency': 'Scheduled',
            'service_address': 'Manhattan',   # incomplete
        }})
        assert r['doc']['service_address'] is None
        assert r['doc']['service_address_text'] == 'Manhattan'
        assert r['doc']['address_needs_review'] == 1
        rj_name.append(r['name'])
    check('incomplete address stored as text', t4)

    # T5: bad customer_id rejected
    def t5():
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_id': 'NONEXISTENT-CUSTOMER-XYZ',
                'caller_phone': '+12125570001',
                'service_state': 'New York',
                'equipment_type': 'Fryer',
                'symptom': 'Test',
                'urgency': 'Scheduled',
            }})
            raise AssertionError('expected error for bad customer_id')
        except ERPNextError as e:
            msg = str(e).lower()
            assert 'no longer exists' in msg or 'does not exist' in msg, \
                f"unexpected error: {e}"
    check('bad customer_id rejected', t5)

    # T6: phone multi-match blocks; force_create_new bypasses
    # Discover non-group Customer Group + Territory once
    groups = call('frappe.client.get_list', {
        'doctype': 'Customer Group',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    if not groups:
        raise AssertionError('No non-group Customer Group - cannot run T6 setup.')
    SAFE_GROUP = groups[0]['name']

    territories = call('frappe.client.get_list', {
        'doctype': 'Territory',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    if not territories:
        raise AssertionError('No non-group Territory - cannot run T6 setup.')
    SAFE_TERRITORY = territories[0]['name']

    def t6():
        t6_suffix = ''.join(random.choices('0123456789', k=4))
        t6_phone = '+1212557' + t6_suffix

        cust1 = call('frappe.client.insert', {'doc': {
            'doctype': 'Customer',
            'customer_name': f"{run_id} MultiMatch A",
            'customer_type': 'Company',
            'customer_group': SAFE_GROUP,
            'territory': SAFE_TERRITORY,
        }})['name']
        cust2 = call('frappe.client.insert', {'doc': {
            'doctype': 'Customer',
            'customer_name': f"{run_id} MultiMatch B",
            'customer_type': 'Company',
            'customer_group': SAFE_GROUP,
            'territory': SAFE_TERRITORY,
        }})['name']
        rj1 = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_id': cust1, 'caller_phone': t6_phone,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'setup A', 'urgency': 'Scheduled',
        }})['name']
        rj2 = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_id': cust2, 'caller_phone': t6_phone,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'setup B', 'urgency': 'Scheduled',
        }})['name']
        rj_name.extend([rj1, rj2])

        # Without force_create_new -> throw
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_name': f"{run_id} MultiMatch Blocked",
                'caller_phone': t6_phone,
                'service_state': 'New York', 'equipment_type': 'Probe',
                'symptom': 'should be blocked', 'urgency': 'Scheduled',
            }})
            raise AssertionError('expected throw on multi-match without force_create_new')
        except ERPNextError as e:
            msg = str(e).lower()
            assert 'matches' in msg or 'ambiguous' in msg, \
                f"unexpected error text: {e}"

        # With force_create_new=true -> succeeds, warning surfaces
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} MultiMatch Forced",
            'caller_phone': t6_phone,
            'force_create_new': True,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'should succeed with force', 'urgency': 'Scheduled',
        }})
        assert r['ok'] is True
        assert any(w.get('kind') == 'phone-multi-match-overridden'
                   for w in r.get('warnings', [])), \
            f"expected phone-multi-match-overridden warning, got {r.get('warnings')}"
        rj_name.append(r['name'])
    check('phone multi-match blocks; force_create_new bypasses', t6)

    # Cleanup
    if not args.keep:
        print("\nCleaning up...")
        _cleanup_run(client, run_id, rj_name)

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, e in failures:
            print(f"  - {name}: {e}")
        sys.exit(1)
    print("\nAll backend smoke checks passed.")


def _cleanup_run(client, run_id, rj_name):
    """Strict order: RJs -> Contacts -> Addresses -> Customers."""
    for name in rj_name:
        try:
            client._request('DELETE', _resource_path('Repair Job', name))
            print(f"  deleted RJ {name}")
        except Exception as e:
            print(f"  cleanup warn: RJ {name}: {e}")

    test_customers = client.list_docs('Customer',
        filters=[['name', 'like', f'%{run_id}%']],
        fields=['name'], limit=50)

    for cust in test_customers:
        try:
            linked_contacts = client.list_docs('Contact',
                filters=[
                    ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                    ['Dynamic Link', 'link_name', '=', cust['name']],
                ],
                fields=['name'], limit=20)
        except Exception:
            linked_contacts = []
        for c in linked_contacts:
            try:
                client._request('DELETE', _resource_path('Contact', c["name"]))
                print(f"  deleted Contact {c['name']}")
            except Exception as e:
                print(f"  cleanup warn: Contact {c['name']}: {e}")

    for cust in test_customers:
        try:
            linked_addrs = client.list_docs('Address',
                filters=[
                    ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                    ['Dynamic Link', 'link_name', '=', cust['name']],
                ],
                fields=['name'], limit=20)
        except Exception:
            linked_addrs = []
        for a in linked_addrs:
            try:
                client._request('DELETE', _resource_path('Address', a["name"]))
                print(f"  deleted Address {a['name']}")
            except Exception as e:
                print(f"  cleanup warn: Address {a['name']}: {e}")

    for cust in test_customers:
        try:
            client._request('DELETE', _resource_path('Customer', cust["name"]))
            print(f"  deleted Customer {cust['name']}")
        except Exception as e:
            print(f"  cleanup warn: Customer {cust['name']}: {e}")


def _clean_stale_test_records(client, hours=24):
    """Pre-run sweep: delete TEST-F-* records older than `hours`."""
    print(f"Pre-run sweep: deleting TEST-F-* records older than {hours}h...")
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    stale_custs = client.list_docs('Customer',
        filters=[
            ['name', 'like', 'TEST-F-%'],
            ['creation', '<', cutoff],
        ],
        fields=['name'], limit=500)
    if not stale_custs:
        print("  (no stale TEST-F-* customers found)\n")
        return

    print(f"  {len(stale_custs)} stale TEST-F-* customers detected")
    for cust in stale_custs:
        rjs = client.list_docs('Repair Job',
            filters=[['customer', '=', cust['name']]],
            fields=['name'], limit=50)
        for rj in rjs:
            try: client._request('DELETE', _resource_path('Repair Job', rj["name"]))
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
                try: client._request('DELETE', _resource_path(ent, e["name"]))
                except Exception: pass
        try: client._request('DELETE', _resource_path('Customer', cust["name"]))
        except Exception as e: print(f"  stale cleanup warn: Customer {cust['name']}: {e}")
    print(f"  swept {len(stale_custs)} stale Customer trees\n")


if __name__ == '__main__':
    main()
