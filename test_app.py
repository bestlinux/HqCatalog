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

if __name__ == "__main__":
    unittest.main()
