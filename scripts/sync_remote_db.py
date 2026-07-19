#!/usr/bin/env python
"""
Sincroniza dados do banco remoto (API em produção) para o banco local.

Uso:
    python scripts/sync_remote_db.py --all
    python scripts/sync_remote_db.py --entities users,occurrences
    python scripts/sync_remote_db.py --list
    python scripts/sync_remote_db.py --entities users --dry-run
    python scripts/sync_remote_db.py --all --page-size 200

Requer variáveis de ambiente:
    API_URL, API_EMAIL, API_PASSWORD
"""

import argparse
import os
import sys
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from core.sync.orchestrator import list_entities, sync_all


def print_progress(entity_key: str, message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    sys.stdout.write(f"\r\033[K[{timestamp}] {message}")
    sys.stdout.flush()


def print_summary(results: dict[str, dict]):
    print("\n\n" + "=" * 60)
    print(f"{'Entidade':<20} {'Status':<12} {'Criados':<10} {'Atualizados':<12}")
    print("-" * 60)
    total_created = 0
    total_updated = 0
    errors = []
    for key, result in results.items():
        status = result.get("status", "?")
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        total_created += created
        total_updated += updated
        print(f"{key:<20} {status:<12} {created:<10} {updated:<12}")
        if status == "error":
            errors.append((key, result.get("error", "")))
    print("-" * 60)
    print(f"{'TOTAL':<20} {'':<12} {total_created:<10} {total_updated:<12}")
    print("=" * 60)
    if errors:
        print("\n❌ Erros:")
        for key, err in errors:
            print(f"  {key}: {err}")
    print(f"\n✅ Sincronização finalizada em {datetime.now().strftime('%H:%M:%S')}")


def main():
    parser = argparse.ArgumentParser(
        description="Sincroniza dados da API remota para o banco local"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Sincroniza todas as entidades",
    )
    group.add_argument(
        "--entities",
        type=str,
        help="Lista de entidades separadas por vírgula (ex: users,posts)",
    )
    group.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Lista entidades disponíveis",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Tamanho da página para requisições paginadas (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exibe o que seria sincronizado sem executar",
    )
    args = parser.parse_args()

    if args.list_only:
        print("Entidades disponíveis para sincronização:\n")
        print(list_entities())
        return

    print(f"🔧 Sincronização iniciada em {datetime.now().strftime('%H:%M:%S')}\n")

    entity_keys = None
    if args.entities:
        entity_keys = [k.strip() for k in args.entities.split(",") if k.strip()]

    try:
        results = sync_all(
            entity_keys=entity_keys,
            page_size=args.page_size,
            dry_run=args.dry_run,
            progress_callback=print_progress,
        )
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}", file=sys.stderr)
        sys.exit(1)

    print_summary(results)


if __name__ == "__main__":
    main()
