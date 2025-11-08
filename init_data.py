import sqlite3
from datetime import datetime, timedelta
import random

def criar_dados_exemplo():
    """Cria dados de exemplo para o sistema"""
    conn = sqlite3.connect('avicena_auth.db')
    cursor = conn.cursor()
    
    # Limpar tabelas existentes
    cursor.execute('DELETE FROM triagens')
    cursor.execute('DELETE FROM pacientes')
    
    # Dados de exemplo para pacientes
    pacientes = [
        ('João Silva', '123.456.789-01', '1980-11-07', 'M', '(11) 91234-5678', '123456789'),  # 45 anos
        ('Maria Souza', '987.654.321-02', '1958-11-07', 'F', '(11) 98765-4321', '987654321'), # 67 anos
        ('Carlos Pereira', '456.789.123-03', '1996-11-07', 'M', '(11) 92222-6666', '456789123'), # 29 anos
        ('Ana Costa', '789.123.456-04', '1971-11-07', 'F', '(11) 95555-9999', '789123456'), # 54 anos
        ('Bruno Lima', '321.654.987-05', '1987-11-07', 'M', '(11) 94444-8888', '321654987'), # 38 anos
        ('Lucia Ferreira', '147.258.369-06', '1995-07-20', 'F', '(11) 93333-7777', '147258369'),
        ('Roberto Santos', '963.852.741-07', '1978-11-18', 'M', '(11) 96666-2222', '963852741'),
        ('Patricia Lima', '852.963.741-08', '1987-06-12', 'F', '(11) 95555-1111', '852963741')
    ]
    
    # Inserir pacientes
    for paciente in pacientes:
        try:
            cursor.execute('''
                INSERT INTO pacientes (nome, cpf, data_nascimento, sexo, telefone, cartao_sus)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', paciente)
        except sqlite3.IntegrityError:
            # Ignora se já existe
            pass
    
    # Dados de exemplo para triagens
    prioridades = ['CRÍTICA', 'ALTA', 'MODERADA', 'BAIXA', 'MÍNIMA']
    status = ['aguardando', 'em_atendimento', 'atendido']
    
    # Pegar IDs dos pacientes e enfermeiros
    cursor.execute('SELECT id FROM pacientes')
    paciente_ids = [row[0] for row in cursor.fetchall()]
    
    cursor.execute("SELECT id FROM usuarios WHERE tipo = 'enfermeiro'")
    enfermeiro_ids = [row[0] for row in cursor.fetchall()]
    
    if paciente_ids and enfermeiro_ids:
        # Criar algumas triagens para cada paciente
        for paciente_id in paciente_ids:
            # Entre 1 e 3 triagens por paciente
            for _ in range(random.randint(1, 3)):
                data_triagem = datetime.now() - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                
                triagem = (
                    paciente_id,
                    random.choice(enfermeiro_ids),
                    round(random.uniform(35.5, 38.5), 1),  # temperatura
                    random.randint(90, 180),  # PA sistólica
                    random.randint(60, 110),  # PA diastólica
                    random.randint(60, 120),  # FC
                    random.randint(12, 25),   # FR
                    random.randint(90, 100),  # SpO2
                    'Dor ' + random.choice(['abdominal', 'torácica', 'lombar', 'de cabeça']),
                    'Paciente ' + random.choice(['estável', 'ansioso', 'agitado', 'calmo']),
                    random.choice(prioridades),
                    random.randint(1, 5),     # score
                    random.choice(status),
                    data_triagem.strftime('%Y-%m-%d %H:%M:%S')
                )
                
                cursor.execute('''
                    INSERT INTO triagens (
                        paciente_id, enfermeiro_id, temperatura,
                        pressao_arterial_sist, pressao_arterial_diast,
                        frequencia_cardiaca, frequencia_respiratoria,
                        saturacao_o2, queixa, observacoes, prioridade,
                        score, status, data_triagem
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', triagem)
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    criar_dados_exemplo()