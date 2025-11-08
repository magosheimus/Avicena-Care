# auth.py - Sistema de Autenticação para Avicena Care
# Desenvolvido para controle de acesso de médicos e enfermeiros
# Versão: 1.0 - 2025

import sqlite3
import hashlib
import secrets
from datetime import datetime
import streamlit as st

class AuthSystem:
    """Sistema de autenticação com controle de acesso por perfil"""
    
    # PINs padrão por tipo de profissional
    DEFAULT_PINS = {
        'medico': 'Med123',
        'enfermeiro': 'Enf123'
    }
    
    # Senhas padrão por tipo de profissional
    DEFAULT_PASSWORDS = {
        'medico': 'medico123',
        'enfermeiro': 'enfermeiro123'
    }
    
    # Lista de usuários padrão
    DEFAULT_USERS = [
        ('medico1', 'medico123', 'Dr. Carlos Silva', 'medico', 'CRM 12345'),
        ('medico2', 'medico123', 'Dra. Ana Santos', 'medico', 'CRM 23456'),
        ('medico3', 'medico123', 'Dr. João Oliveira', 'medico', 'CRM 34567'),
        ('enfermeiro1', 'enfermeiro123', 'Enf. Maria Lima', 'enfermeiro', 'COREN 45678'),
        ('enfermeiro2', 'enfermeiro123', 'Enf. Pedro Costa', 'enfermeiro', 'COREN 56789'),
        ('enfermeiro3', 'enfermeiro123', 'Enf. Julia Ferreira', 'enfermeiro', 'COREN 67890')
    ]
    
    def __init__(self, db_path="avicena_auth.db"):
        """Inicializa o sistema de autenticação"""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Inicializa o banco de dados de autenticação"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Remove tabelas existentes para garantir consistência
        cursor.execute("DROP TABLE IF EXISTS usuarios")
        cursor.execute("DROP TABLE IF EXISTS pacientes")
        cursor.execute("DROP TABLE IF EXISTS triagens")
        cursor.execute("DROP TABLE IF EXISTS log_acessos")
        cursor.execute("DROP TABLE IF EXISTS chaves_acesso")
        
        # Tabela de usuários
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL,
                registro_profissional TEXT,
                ativo INTEGER DEFAULT 1,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ultimo_acesso TIMESTAMP
            )
        ''')
        
        # Criar usuários padrão
        for username, senha, nome, tipo, registro in self.DEFAULT_USERS:
            password_hash = hashlib.sha256(senha.encode()).hexdigest()
            user_id = secrets.token_hex(16)
            cursor.execute('''
                INSERT INTO usuarios (id, username, password_hash, nome, tipo, registro_profissional)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, password_hash, nome, tipo, registro))
        
        # Tabela de pacientes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pacientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT UNIQUE,
                data_nascimento DATE,
                sexo TEXT,
                endereco TEXT,
                telefone TEXT,
                cartao_sus TEXT,
                email TEXT,
                status TEXT DEFAULT 'ativo',
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de triagens
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS triagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id INTEGER,
                enfermeiro_id TEXT,
                temperatura REAL,
                pressao_arterial_sist INTEGER,
                pressao_arterial_diast INTEGER,
                frequencia_cardiaca INTEGER,
                frequencia_respiratoria INTEGER,
                saturacao_o2 INTEGER,
                queixa TEXT,
                observacoes TEXT,
                prioridade TEXT,
                score INTEGER,
                status TEXT DEFAULT 'aguardando',
                data_triagem TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paciente_id) REFERENCES pacientes(id),
                FOREIGN KEY (enfermeiro_id) REFERENCES usuarios(id)
            )
        ''')
        
        # Tabela de log
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS log_acessos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id TEXT,
                tipo_evento TEXT,
                detalhes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def authenticate(self, username, password, pin=None):
        """Autentica um usuário com base no username e senha/PIN"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, username, password_hash, nome, tipo, registro_profissional
            FROM usuarios
            WHERE username = ? AND ativo = 1
        """, (username,))
        
        user = cursor.fetchone()
        if not user:
            conn.close()
            return None
            
        user_type = user[4]  # tipo do usuário
            
        # Se um PIN foi fornecido, verifica se corresponde ao tipo de usuário
        if pin:
            if pin != self.DEFAULT_PINS.get(user_type):
                conn.close()
                return None
        # Se não foi fornecido PIN, verifica a senha
        elif password:
            expected_password = self.DEFAULT_PASSWORDS.get(user_type)
            if password != expected_password:
                conn.close()
                return None
        else:
            conn.close()
            return None
            
        # Atualiza último acesso
        cursor.execute("""
            UPDATE usuarios
            SET ultimo_acesso = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (user[0],))
        
        # Registra o acesso no log
        cursor.execute("""
            INSERT INTO log_acessos (usuario_id, tipo_evento, detalhes)
            VALUES (?, 'login', ?)
        """, (user[0], f"Login bem-sucedido para {user[3]}"))
        
        conn.commit()
        conn.close()
        
        return {
            'id': user[0],
            'username': user[1],
            'nome': user[3],
            'tipo': user[4],
            'registro': user[5]
        }
    
    def buscar_paciente(self, termo_busca):
        """
        Busca pacientes por nome, CPF ou cartão SUS
        
        Args:
            termo_busca: Termo para buscar (nome, CPF ou cartão SUS)
            
        Returns:
            Lista de pacientes encontrados
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Adiciona wildcards para busca parcial
        termo = f"%{termo_busca}%"
        
        cursor.execute("""
            SELECT id, nome, cpf, data_nascimento, sexo, telefone, cartao_sus
            FROM pacientes
            WHERE nome LIKE ? OR cpf LIKE ? OR cartao_sus LIKE ?
            ORDER BY nome
        """, (termo, termo, termo))
        
        resultados = cursor.fetchall()
        conn.close()
        
        # Converte resultados para lista de dicionários
        pacientes = []
        for row in resultados:
            pacientes.append({
                'id': row[0],
                'nome': row[1],
                'cpf': row[2],
                'data_nascimento': row[3],
                'sexo': row[4],
                'telefone': row[5],
                'cartao_sus': row[6]
            })
            
        return pacientes