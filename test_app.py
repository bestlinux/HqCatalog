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

    def test_resenha_functionality(self):
        # 1. Salvar com resenha inicial
        database.salvar_hqs([
            {
                "titulo": "Watchmen",
                "edicao": "Edição Definitiva",
                "editora": "Panini",
                "resenha": "Uma obra-prima absoluta dos quadrinhos."
            }
        ], "Estante 1", self.test_db)

        hq = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq["resenha"], "Uma obra-prima absoluta dos quadrinhos.")

        # 2. Atualizar resenha diretamente
        database.definir_resenha(1, "Roteiro genial de Alan Moore e arte impecável de Dave Gibbons.", self.test_db)
        hq_updated = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_updated["resenha"], "Roteiro genial de Alan Moore e arte impecável de Dave Gibbons.")

        # 3. Busca por texto dentro da resenha
        df_busca = database.listar_todas_hqs(busca="Alan Moore", db_path=self.test_db)
        self.assertEqual(len(df_busca), 1)

    def test_resumo_functionality(self):
        # 1. Salvar com resumo inicial gerado pela IA
        database.salvar_hqs([
            {
                "titulo": "Demolidor: A Queda de Murdock",
                "edicao": "Edição de Luxo",
                "editora": "Panini",
                "resumo": "Karen Page vende a identidade do Demolidor e o Rei do Crime destrói a vida de Matt Murdock."
            }
        ], "Estante 1", self.test_db)

        hq = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq["resumo"], "Karen Page vende a identidade do Demolidor e o Rei do Crime destrói a vida de Matt Murdock.")

        # 2. Atualizar resumo diretamente
        database.definir_resumo(1, "A mais aclamada fase do Demolidor por Frank Miller e David Mazzucchelli.", self.test_db)
        hq_updated = database.obter_hq_por_id(1, self.test_db)
        self.assertEqual(hq_updated["resumo"], "A mais aclamada fase do Demolidor por Frank Miller e David Mazzucchelli.")

        # 3. Busca por termo dentro do resumo
        df_busca = database.listar_todas_hqs(busca="Mazzucchelli", db_path=self.test_db)
        self.assertEqual(len(df_busca), 1)

    def test_duplicate_detection(self):
        # 1. Salvar primeira edição
        res1 = database.salvar_hqs([
            {"titulo": "Homem-Aranha", "edicao": "#1", "editora": "Panini"}
        ], "Estante 1", self.test_db, retornar_detalhes=True)
        self.assertEqual(res1["salvos"], 1)
        self.assertEqual(res1["duplicados"], 0)

        # 2. Tentar salvar a mesma edição (#1 Panini) - deve ser ignorada como duplicada
        res2 = database.salvar_hqs([
            {"titulo": "homem-aranha", "edicao": "#1 ", "editora": "PANINI"}
        ], "Estante 1", self.test_db, retornar_detalhes=True)
        self.assertEqual(res2["salvos"], 0)
        self.assertEqual(res2["duplicados"], 1)

        # 3. Salvar número diferente (#2 Panini) - DEVE ser salvo com sucesso
        res3 = database.salvar_hqs([
            {"titulo": "Homem-Aranha", "edicao": "#2", "editora": "Panini"}
        ], "Estante 1", self.test_db, retornar_detalhes=True)
        self.assertEqual(res3["salvos"], 1)
        self.assertEqual(res3["duplicados"], 0)

        # 4. Salvar mesma edição (#1) mas de outra Editora ("Abril") - DEVE ser salvo
        res4 = database.salvar_hqs([
            {"titulo": "Homem-Aranha", "edicao": "#1", "editora": "Abril"}
        ], "Estante 2", self.test_db, retornar_detalhes=True)
        self.assertEqual(res4["salvos"], 1)
        self.assertEqual(res4["duplicados"], 0)

        # 5. Salvar lote misto com duplicadas internas e do banco
        res5 = database.salvar_hqs([
            {"titulo": "Homem-Aranha", "edicao": "#1", "editora": "Panini"}, # duplicada do banco
            {"titulo": "Homem-Aranha", "edicao": "#3", "editora": "Panini"}, # nova 1
            {"titulo": "Homem-Aranha", "edicao": "#3", "editora": "Panini"}, # duplicada no mesmo lote
            {"titulo": "Batman", "edicao": "Vol. 1", "editora": "Panini"}    # nova 2
        ], "Estante 1", self.test_db, retornar_detalhes=True)
        self.assertEqual(res5["salvos"], 2)
        self.assertEqual(res5["duplicados"], 2)

    def test_chatbot_helpers(self):
        # 1. Contexto vazio
        contexto_vazio = database.obter_contexto_hqs_para_chat(self.test_db)
        self.assertEqual(len(contexto_vazio), 0)
        resp_vazia = gemini_service.consultar_chatbot_colecao("Indique algo de história", contexto_vazio)
        self.assertIn("vazio", resp_vazia.lower())

        # 2. Contexto populado
        database.salvar_hqs([
            {
                "titulo": "Cumbe",
                "edicao": "Única",
                "editora": "Veneta",
                "genero": "Histórico",
                "resumo": "Histórias sobre a resistência contra a escravidão no Brasil colonial."
            }
        ], "Estante Histórica", self.test_db)

        contexto_populado = database.obter_contexto_hqs_para_chat(self.test_db)
        self.assertEqual(len(contexto_populado), 1)
        self.assertEqual(contexto_populado[0]["titulo"], "Cumbe")
        self.assertIn("resistência", contexto_populado[0]["resumo"])

    def test_sorting_functionality(self):
        database.salvar_hqs([
            {"titulo": "Zagor", "edicao": "#1", "editora": "Mythos"},
            {"titulo": "Akira", "edicao": "#1", "editora": "JBC"},
            {"titulo": "Batman", "edicao": "#1", "editora": "Panini"}
        ], "Estante Teste", self.test_db)

        # 1. Ordem Alfabética A-Z (padrão)
        df_asc = database.listar_todas_hqs(ordem_por="titulo_asc", db_path=self.test_db)
        titulos_asc = list(df_asc["titulo"])
        self.assertEqual(titulos_asc, ["Akira", "Batman", "Zagor"])

        # 2. Ordem Alfabética Z-A
        df_desc = database.listar_todas_hqs(ordem_por="titulo_desc", db_path=self.test_db)
        titulos_desc = list(df_desc["titulo"])
        self.assertEqual(titulos_desc, ["Zagor", "Batman", "Akira"])

        # 3. Mais Recentes (ID Desc)
        df_id_desc = database.listar_todas_hqs(ordem_por="id_desc", db_path=self.test_db)
        self.assertEqual(list(df_id_desc["titulo"]), ["Batman", "Akira", "Zagor"])

    def test_wishlist_and_price_search(self):
        # 1. Testar intenção de busca de preço
        self.assertTrue(gemini_service.eh_intencao_pesquisa_preco("Pesquise Flash Omnibus Volume 1"))
        self.assertTrue(gemini_service.eh_intencao_pesquisa_preco("Qual o preço de Watchmen?"))
        self.assertTrue(gemini_service.eh_intencao_pesquisa_preco("Preço na Comix ou Mundos Infinitos"))
        self.assertFalse(gemini_service.eh_intencao_pesquisa_preco("Quero ler algo de terror"))

        # 2. Testar geração de links das 5 lojas
        link_amz = gemini_service.gerar_link_loja("Amazon", "Flash Omnibus")
        link_magalu = gemini_service.gerar_link_loja("MagazineLuiza", "Flash Omnibus")
        link_ml = gemini_service.gerar_link_loja("MercadoLivre", "Flash Omnibus")
        link_mi = gemini_service.gerar_link_loja("Mundos Infinitos", "Flash Omnibus")
        link_comix = gemini_service.gerar_link_loja("Comix Book Shop", "Flash Omnibus")

        self.assertIn("amazon.com.br", link_amz)
        self.assertIn("magazineluiza.com.br", link_magalu)
        self.assertIn("mercadolivre.com.br", link_ml)
        self.assertIn("mundosinfinitos.com.br", link_mi)
        self.assertIn("comix.com.br", link_comix)

        # 3. Adicionar na Lista de Desejos com Link de Oferta
        item_id = database.adicionar_item_lista_desejos(
            titulo="Flash Omnibus",
            edicao="Volume 1",
            editora="Panini",
            melhor_preco=140.0,
            melhor_loja="MagazineLuiza",
            link_oferta=link_magalu,
            observacoes="Melhor oferta encontrada",
            db_path=self.test_db
        )
        self.assertGreater(item_id, 0)

        # 4. Listar e Obter Lista de Desejos
        df_desejos = database.listar_lista_desejos(self.test_db)
        self.assertEqual(len(df_desejos), 1)
        item = df_desejos.iloc[0]
        self.assertEqual(item["titulo"], "Flash Omnibus")
        self.assertEqual(item["melhor_loja"], "MagazineLuiza")
        self.assertEqual(item["melhor_preco"], 140.0)
        self.assertEqual(item["link_oferta"], link_magalu)

        # 5. Obter item específico
        item_obtido = database.obter_item_lista_desejos(item_id, self.test_db)
        self.assertIsNotNone(item_obtido)
        self.assertEqual(item_obtido["titulo"], "Flash Omnibus")

        # 6. Atualizar item da Lista de Desejos
        updated = database.atualizar_item_lista_desejos(
            item_id=item_id,
            titulo="Flash por Geoff Johns Omnibus",
            melhor_preco=135.50,
            melhor_loja="Amazon",
            link_oferta=link_amz,
            observacoes="Preço baixou na Amazon!",
            db_path=self.test_db
        )
        self.assertTrue(updated)
        item_apos_update = database.obter_item_lista_desejos(item_id, self.test_db)
        self.assertEqual(item_apos_update["titulo"], "Flash por Geoff Johns Omnibus")
        self.assertEqual(item_apos_update["melhor_preco"], 135.50)
        self.assertEqual(item_apos_update["melhor_loja"], "Amazon")
        self.assertEqual(item_apos_update["link_oferta"], link_amz)

        # 7. Deletar item da Lista de Desejos
        deleted = database.deletar_item_lista_desejos(item_id, self.test_db)
        self.assertTrue(deleted)
        df_apos_del = database.listar_lista_desejos(self.test_db)
        self.assertEqual(len(df_apos_del), 0)

    def test_bulk_status_update_and_bulk_deletion(self):
        # 1. Inserir 4 HQs de teste
        database.salvar_hqs([
            {"titulo": "Batman #1", "lido": "Não Lido"},
            {"titulo": "Batman #2", "lido": "Não Lido"},
            {"titulo": "Batman #3", "lido": "Não Lido"},
            {"titulo": "Batman #4", "lido": "Lido"},
        ], "Estante Morcego", self.test_db)

        df = database.listar_todas_hqs(db_path=self.test_db)
        self.assertEqual(len(df), 4)

        # 2. Alteração em massa para 'Lido' (HQs 1 e 2)
        qtd_alteradas = database.atualizar_status_leitura_em_massa([1, 2], "Lido", self.test_db)
        self.assertEqual(qtd_alteradas, 2)
        hq1 = database.obter_hq_por_id(1, self.test_db)
        hq2 = database.obter_hq_por_id(2, self.test_db)
        self.assertEqual(hq1["lido"], "Lido")
        self.assertEqual(hq2["lido"], "Lido")

        # 3. Alteração em massa para 'Não Lido' (HQs 1 e 4)
        qtd_alteradas_nl = database.atualizar_status_leitura_em_massa([1, 4], "Não Lido", self.test_db)
        self.assertEqual(qtd_alteradas_nl, 2)
        hq1_nl = database.obter_hq_por_id(1, self.test_db)
        hq4_nl = database.obter_hq_por_id(4, self.test_db)
        self.assertEqual(hq1_nl["lido"], "Não Lido")
        self.assertEqual(hq4_nl["lido"], "Não Lido")

        # 4. Exclusão em massa (HQs 2 e 3)
        qtd_deletadas = database.deletar_hqs_em_massa([2, 3], self.test_db)
        self.assertEqual(qtd_deletadas, 2)
        df_restante = database.listar_todas_hqs(db_path=self.test_db)
        self.assertEqual(len(df_restante), 2)
        ids_restantes = [r["id"] for _, r in df_restante.iterrows()]
        self.assertEqual(ids_restantes, [1, 4])

if __name__ == "__main__":
    unittest.main()

