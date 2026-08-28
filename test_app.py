import unittest
import os
import database
import gemini_service

class TestHqCatalog(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_inventario_temp.db"
        database.init_db(self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_database_flow(self):
        items = [
            {"titulo": "Watchmen", "edicao": "Edição Definitiva", "editora": "Panini"},
            {"titulo": "Akira", "edicao": "Vol. 1", "editora": "JBC"},
            {"titulo": "Sandman", "edicao": "Vol. 1", "editora": "Panini"}
        ]
        inserted = database.salvar_hqs(items, "Estante A - Prateleira 1", self.test_db)
        self.assertEqual(inserted, 3)

        shelves = database.obter_prateleiras(self.test_db)
        self.assertIn("Estante A - Prateleira 1", shelves)

        stats = database.obter_estatisticas(self.test_db)
        self.assertEqual(stats["total_hqs"], 3)
        self.assertEqual(stats["total_prateleiras"], 1)
        self.assertEqual(stats["total_editoras"], 2)

    def test_database_edit(self):
        database.salvar_hqs([{"titulo": "Batman", "edicao": "1", "editora": "Panini"}], "Prateleira 1", self.test_db)
        hq = database.obter_hq_por_id(1, self.test_db)
        self.assertIsNotNone(hq)
        self.assertEqual(hq["titulo"], "Batman")

        updated = database.atualizar_hq(
            hq_id=1,
            titulo="Batman: Cavaleiro das Trevas",
            edicao="Edição Especial",
            editora="Panini Comics",
            prateleira="Prateleira 2",
            db_path=self.test_db
        )
        self.assertTrue(updated)

        hq_editado = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_editado["titulo"], "Batman: Cavaleiro das Trevas")
        self.assertEqual(hq_editado["edicao"], "Edição Especial")
        self.assertEqual(hq_editado["prateleira"], "Prateleira 2")

    def test_reading_status_and_stats(self):
        database.salvar_hqs([
            {"titulo": "Gibi 1", "edicao": "1", "editora": "Panini"},
            {"titulo": "Gibi 2", "edicao": "2", "editora": "Panini"}
        ], "Estante 1", self.test_db)

        hq = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq["lido"], "Não Lido")

        novo_status = database.alternar_status_leitura(1, self.test_db)
        self.assertEqual(novo_status, "Lido")

        hq_atualizado = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_atualizado["lido"], "Lido")

        stats = database.obter_estatisticas(self.test_db)
        self.assertEqual(stats["total_lidos"], 1)
        self.assertEqual(stats["total_nao_lidos"], 1)

    def test_json_parser_variations(self):
        # Test markdown code block
        sample_md = """```json
[
  {"titulo": "Demolidor", "edicao": "1", "editora": "Marvel", "genero": "Super-heróis"},
  {"titulo": "Uzumaki", "edicao": "1", "editora": "Devir", "genero": "Terror"}
]
```"""
        parsed = gemini_service.limpar_e_parsear_json(sample_md)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["titulo"], "Demolidor")
        self.assertEqual(parsed[0]["genero"], "Super-heróis")
        self.assertEqual(parsed[1]["editora"], "Devir")
        self.assertEqual(parsed[1]["genero"], "Terror")

        # Test bare json
        sample_bare = '[{"titulo": "Turma da Monica", "edicao": "100", "editora": "Panini", "genero": "Infantil"}]'
        parsed_bare = gemini_service.limpar_e_parsear_json(sample_bare)
        self.assertEqual(len(parsed_bare), 1)
        self.assertEqual(parsed_bare[0]["titulo"], "Turma da Monica")
        self.assertEqual(parsed_bare[0]["genero"], "Infantil")

    def test_authors_and_search(self):
        database.salvar_hqs([
            {
                "titulo": "Watchmen",
                "edicao": "Edição Definitiva",
                "editora": "Panini",
                "genero": "Super-heróis",
                "escritor": "Alan Moore",
                "ilustrador": "Dave Gibbons"
            }
        ], "Estante 1", self.test_db)

        # Busca por escritor
        df_alan = database.listar_todas_hqs(busca="Alan Moore", db_path=self.test_db)
        self.assertEqual(len(df_alan), 1)
        
        hq_row = df_alan.iloc[0] if hasattr(df_alan, "iloc") else df_alan[0]
        self.assertEqual(hq_row["escritor"], "Alan Moore")
        self.assertEqual(hq_row["ilustrador"], "Dave Gibbons")

        # Atualização de escritor e ilustrador
        database.atualizar_hq(
            hq_id=int(hq_row["id"]),
            titulo="Watchmen",
            edicao="Edição Definitiva",
            editora="Panini",
            genero="Super-heróis",
            escritor="Alan Moore",
            ilustrador="Dave Gibbons & John Higgins",
            prateleira="Estante 1",
            db_path=self.test_db
        )
        hq_updated = database.obter_hq_por_id(int(hq_row["id"]), self.test_db)
        self.assertEqual(hq_updated["ilustrador"], "Dave Gibbons & John Higgins")

    def test_rating_functionality(self):
        # 1. Inserção com avaliação padrão (0) e com nota pré-definida (5)
        database.salvar_hqs([
            {"titulo": "HQ Sem Nota", "edicao": "1", "editora": "Panini"},
            {"titulo": "HQ Nota 5", "edicao": "1", "editora": "Panini", "avaliacao": 5},
            {"titulo": "HQ Nota 4", "edicao": "2", "editora": "Mythos", "avaliacao": 4}
        ], "Estante Rating", self.test_db)

        # Checa valor padrão
        hq_sem_nota = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_sem_nota["avaliacao"], 0)

        hq_5 = database.obter_hq_por_id(2, self.test_db)
        self.assertEqual(hq_5["avaliacao"], 5)

        # 2. Definir avaliação direta
        success = database.definir_avaliacao(1, 3, self.test_db)
        self.assertTrue(success)
        hq_1_atualizado = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_1_atualizado["avaliacao"], 3)

        # 3. Clamping de avaliação (ex: nota 10 vira 5, nota negativa vira 0)
        database.definir_avaliacao(1, 10, self.test_db)
        self.assertEqual(database.obter_hq_por_id(1, self.test_db)["avaliacao"], 5)

        # 4. Estatísticas de avaliação
        stats = database.obter_estatisticas(self.test_db)
        # Itens: HQ 1 (5), HQ 2 (5), HQ 3 (4) -> Média = (5 + 5 + 4) / 3 = 4.666 -> 4.7
        self.assertEqual(stats["total_avaliados"], 3)
        self.assertEqual(stats["media_avaliacao"], 4.7)

        # 5. Filtro por avaliação
        df_nota_4 = database.listar_todas_hqs(avaliacao_filtro=4, db_path=self.test_db)
        self.assertEqual(len(df_nota_4), 1)
        row = df_nota_4.iloc[0] if hasattr(df_nota_4, "iloc") else df_nota_4[0]
        self.assertEqual(row["titulo"], "HQ Nota 4")

    def test_manual_cover_functionality(self):
        database.salvar_hqs([
            {"titulo": "Homem-Aranha", "edicao": "1", "editora": "Panini"}
        ], "Estante Spider", self.test_db)

        # Sem capa inicialmente
        hq = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq.get("capa"), "")

        # Cadastrar capa manual
        fake_b64_img = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBD..."
        success = database.definir_capa(1, fake_b64_img, self.test_db)
        self.assertTrue(success)

        hq_com_capa = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_com_capa.get("capa"), fake_b64_img)

        # Remover capa
        removed = database.remover_capa_hq(1, self.test_db)
        self.assertTrue(removed)
        hq_sem_capa = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_sem_capa.get("capa"), "")

    def test_auth_module(self):
        import auth
        # 1. Credenciais padrão de fallback
        os.environ.pop("APP_USERNAME", None)
        os.environ.pop("APP_PASSWORD", None)
        u, p = auth.obter_credenciais_configuradas()
        self.assertEqual(u, "admin")
        self.assertEqual(p, "admin123")

        self.assertTrue(auth.verificar_credenciais("admin", "admin123"))
        self.assertTrue(auth.verificar_credenciais(" ADMIN ", "admin123")) # case insensitive user
        self.assertFalse(auth.verificar_credenciais("admin", "senha_errada"))
        self.assertFalse(auth.verificar_credenciais("hacker", "admin123"))

        # 2. Credenciais customizadas via ENV
        os.environ["APP_USERNAME"] = "colecionador"
        os.environ["APP_PASSWORD"] = "batman2026"
        u_cust, p_cust = auth.obter_credenciais_configuradas()
        self.assertEqual(u_cust, "colecionador")
        self.assertEqual(p_cust, "batman2026")
        self.assertTrue(auth.verificar_credenciais("colecionador", "batman2026"))
        self.assertFalse(auth.verificar_credenciais("admin", "admin123"))

if __name__ == "__main__":
    unittest.main()
