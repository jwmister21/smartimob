import sqlite3

# Ajuste para o caminho real do seu banco
conn = sqlite3.connect("database/imobiliaria.db") 
cursor = conn.cursor()

try:
    # Adicionando a coluna para o link da foto
    cursor.execute("ALTER TABLE usuarios ADD COLUMN foto_url TEXT")
    conn.commit()
    print("Coluna 'foto_url' adicionada com sucesso!")
except sqlite3.OperationalError:
    print("A coluna 'foto_url' já existe no banco.")

conn.close()