"""
Script Utilitário para Sincronização de Banco de Dados:
- Enviar Local -> Turso Cloud (--upload)
- Baixar Turso Cloud -> Local (--download)
Cria automaticamente cópia de segurança antes de sobrescrever.
"""

import sys
import os
import argparse
import sqlite3

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Garante importações relativas corretas
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database


def barra_progresso(acao: str, atual: int, total: int):
    pct = (atual / total) * 100 if total > 0 else 100
    bloco = int(pct // 4)
    barra = "#" * bloco + "-" * (25 - bloco)
    print(f"\r -> {acao}: [{barra}] {atual:,}/{total:,} HQs ({pct:.1f}%)", end="", flush=True)


def executar_upload():
    print("=" * 60)
    print(" [HQ CATALOG] Sincronização: SQLite Local -> Turso Cloud")
    print("=" * 60)

    url, token = database.get_turso_credentials(ignorar_flag_local=True)
    if not url or not token:
        print("\n[ERRO] O Turso Cloud não está configurado.")
        print("Verifique se as variáveis TURSO_DATABASE_URL e TURSO_AUTH_TOKEN")
        print("estão presentes e ativas no seu arquivo .env.")
        sys.exit(1)

    if not os.path.exists(database.DB_DEFAULT_PATH):
        print(f"\n[ERRO] Arquivo de banco local '{database.DB_DEFAULT_PATH}' não encontrado.")
        sys.exit(1)

    # Contagem local
    conn_local = sqlite3.connect(database.DB_DEFAULT_PATH)
    cur = conn_local.cursor()
    total_local = cur.execute("SELECT COUNT(*) FROM hqs").fetchone()[0]
    conn_local.close()

    print(f"\n[1/3] Banco Local pronto: {total_local:,} HQs identificadas.")
    print("      Conectando e verificando integridade do Turso Cloud...")

    def _prog(atual, total):
        barra_progresso("Enviando para a Nuvem", atual, total)

    print("\n[2/3] Criando backup de segurança da Nuvem e enviando dados locais...")
    try:
        resultado = database.sincronizar_local_para_turso(
            db_origem_path=database.DB_DEFAULT_PATH,
            fazer_backup_turso_previo=True,
            tamanho_lote=100,
            progresso_callback=_prog
        )
        print("\n\n" + "=" * 60)
        print(" [SUCESSO] SINCRONIZAÇÃO PARA TURSO CLOUD CONCLUÍDA!")
        print("=" * 60)
        print(f" * HQs enviadas para Nuvem:      {resultado['hqs']:,}")
        print(f" * Prateleiras enviadas:         {resultado['prateleiras']:,}")
        print(f" * Itens na lista de desejos:    {resultado['lista_desejos']:,}")
        print(f" * Histórico de destaques:       {resultado['historico_destaques']:,}")
        print(f" * Tempo total:                  {resultado['tempo_segundos']:.2f} segundos")
        if resultado.get("backup_turso_path"):
            print(f" * Backup prévio da nuvem salvo: {resultado['backup_turso_path']}")
        print(f" * Banco de Nuvem ativo e atualizado!")
        print("=" * 60)
    except Exception as e:
        print(f"\n[ERRO] Falha durante a sincronização: {e}")
        sys.exit(1)


def executar_download():
    print("=" * 60)
    print(" [HQ CATALOG] Sincronização: Turso Cloud -> SQLite Local")
    print("=" * 60)

    url, token = database.get_turso_credentials(ignorar_flag_local=True)
    if not url or not token:
        print("\n[ERRO] O Turso Cloud não está configurado.")
        print("Verifique se as variáveis TURSO_DATABASE_URL e TURSO_AUTH_TOKEN")
        print("estão presentes no seu arquivo .env.")
        sys.exit(1)

    print("\n[1/3] Conectando ao Turso Cloud...")
    try:
        res_count = database.executar_turso_query("SELECT COUNT(*) FROM hqs", ignorar_flag_local=True)
        total_hqs = res_count.rows[0][0] if res_count.rows else 0
        print(f" -> Total de HQs identificadas na Nuvem: {total_hqs:,}")
    except Exception as e:
        print(f"[ERRO] Falha ao consultar Turso Cloud: {e}")
        sys.exit(1)

    def _prog(atual, total):
        barra_progresso("Baixando da Nuvem", atual, total)

    print("\n[2/3] Iniciando sincronização e gerando backup local prévio...")
    try:
        resultado = database.sincronizar_turso_para_local(
            db_destino_path=database.DB_DEFAULT_PATH,
            fazer_backup_previo=True,
            tamanho_lote=500,
            progresso_callback=_prog
        )
        print("\n\n" + "=" * 60)
        print(" [SUCESSO] SINCRONIZAÇÃO CONCLUÍDA COM SUCESSO!")
        print("=" * 60)
        print(f" * HQs replicadas:           {resultado['hqs']:,}")
        print(f" * Prateleiras replicadas:   {resultado['prateleiras']:,}")
        print(f" * Lista de desejos:         {resultado['lista_desejos']:,}")
        print(f" * Histórico de destaques:   {resultado['historico_destaques']:,}")
        print(f" * Tempo total gasto:        {resultado['tempo_segundos']:.2f} segundos")
        if resultado.get("backup_path"):
            print(f" * Cópia de segurança salva: {resultado['backup_path']}")
        print(f" * Arquivo local atualizado: {database.DB_DEFAULT_PATH}")
        print("=" * 60)
    except Exception as e:
        print(f"\n[ERRO] Falha durante a sincronização: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Sincronizador HqCatalog (Local <-> Turso Cloud)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--upload", "-u", action="store_true", help="Envia o banco SQLite local para o Turso Cloud")
    group.add_argument("--download", "-d", action="store_true", help="Baixa o catálogo do Turso Cloud para o SQLite local")
    args = parser.parse_args()

    if args.upload:
        executar_upload()
    elif args.download:
        executar_download()
    else:
        # Modo interativo se chamado sem argumentos
        print("=" * 60)
        print(" [HQ CATALOG] Sincronização de Banco de Dados")
        print("=" * 60)
        print("Escolha a direção da sincronização:")
        print(" [1] Enviar SQLite Local -> Turso Cloud (Upload)")
        print(" [2] Baixar Turso Cloud -> SQLite Local (Download)")
        print(" [0] Cancelar")
        print("=" * 60)
        escolha = input("Digite a opção desejada [1/2/0]: ").strip()
        if escolha == "1":
            executar_upload()
        elif escolha == "2":
            executar_download()
        else:
            print("Operação cancelada pelo usuário.")
            sys.exit(0)


if __name__ == "__main__":
    main()
