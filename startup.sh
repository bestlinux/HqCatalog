#!/bin/bash

# Ativa o ambiente virtual do Azure App Service (Oryx) se existir
if [ -d "/antenv" ]; then
    source /antenv/bin/activate
elif [ -d "$HOME/antenv" ]; then
    source $HOME/antenv/bin/activate
fi

# Garante que as dependências estejam presentes caso o build não tenha rodado
pip install -r requirements.txt

# Inicia o Streamlit na porta 8000 com suporte a WebSockets e sem restrição de CORS
python -m streamlit run app.py \
    --server.port 8000 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false
