#!/usr/bin/env python3
"""
Simulador de Hospital usando threads e semáforos para controle de recursos
"""
import threading
import time
import random
from datetime import datetime

# Configuração dos recursos e parâmetros
N_MEDICOS = 5
N_SALAS_CIRURGIA = 2
N_LEITOS = 10
N_PACIENTES = 10  # Reduzido para melhor visualização

# Tempos de cada procedimento (em segundos)
TEMPO_CONSULTA_MIN, TEMPO_CONSULTA_MAX = 30.0, 45.0
TEMPO_EXAME_MIN, TEMPO_EXAME_MAX = 25.0, 35.0
TEMPO_CIRURGIA_MIN, TEMPO_CIRURGIA_MAX = 40.0, 60.0
TEMPO_LEITO_MIN, TEMPO_LEITO_MAX = 35.0, 50.0

# Probabilidades dos procedimentos
P_PROB_EXAME = 0.6
P_PROB_CIRURGIA = 0.3
P_PROB_CIRURGIA_DIRECT = 0.05

# Semáforos para controle de recursos
medicos_sem = threading.Semaphore(N_MEDICOS)
salas_sem = threading.Semaphore(N_SALAS_CIRURGIA)
leitos_sem = threading.Semaphore(N_LEITOS)

# Lock para imprimir sem entrelaçar linhas
print_lock = threading.Lock()

class Colors:
    PACIENTE = '\033[94m'
    MEDICO = '\033[92m'
    SALA = '\033[95m'
    LEITO = '\033[93m'
    RESET = '\033[0m'

# Função de log com timestamp, cores e delay
def log(msg):
    with print_lock:
        ts = datetime.now().strftime("%H:%M:%S")
        # Adiciona cores baseado no tipo de mensagem
        if "médico" in msg.lower():
            color = Colors.MEDICO
        elif "sala" in msg.lower():
            color = Colors.SALA
        elif "leito" in msg.lower():
            color = Colors.LEITO
        else:
            color = Colors.PACIENTE
            
        print(f"[{ts}] {color}{msg}{Colors.RESET}")
        # Pequeno delay após cada log para melhor visualização
        time.sleep(0.5)  # Aumentado o delay entre mensagens para 0.5 segundos
        print("----------------------------")

# -------------------------
# Classe Patient
# -------------------------
class Patient:
    def __init__(self, pid):
        self.pid = pid # ID do paciente
        # eventos para encadear atividades (simula threads dentro de um "processo")
        self.consulta_done = threading.Event()
        self.exames_done = threading.Event()
        self.cirurgia_done = threading.Event()
        self.leito_done = threading.Event()

    def start(self):
        # Inicia a "execução do processo paciente" criando uma thread principal
        t = threading.Thread(target=self.run_process, name=f"Paciente-{self.pid}")
        t.start()
        return t

    def run_process(self):
        consulta_thread = threading.Thread(target=self.thread_consulta, name=f"Consulta-{self.pid}")
        consulta_thread.start()
        self.consulta_done.wait()
        log(f"Paciente {self.pid} finalizou sua consulta inicial")

        # Decide o fluxo do paciente
        fazer_exame = random.random() < P_PROB_EXAME
        fazer_cirurgia = False

        # pequena chance de ir direto pra cirurgia sem exames
        if random.random() < P_PROB_CIRURGIA_DIRECT:
            fazer_cirurgia = True

        # se fez exames, então cirurgia pode vir depois dos exames
        if fazer_exame:
            exame_thread = threading.Thread(target=self.thread_exame, name=f"Exame-{self.pid}")
            exame_thread.start()
            self.exames_done.wait()
            # após exames, decidir se precisa cirurgia
            if random.random() < P_PROB_CIRURGIA:
                fazer_cirurgia = True

        # se precisa cirurgia, executa
        if fazer_cirurgia:
            cirurgia_thread = threading.Thread(target=self.thread_cirurgia, name=f"Cirurgia-{self.pid}")
            cirurgia_thread.start()
            self.cirurgia_done.wait()
            # após cirurgia, precisa de leito
            leito_thread = threading.Thread(target=self.thread_leito, name=f"Leito-{self.pid}")
            leito_thread.start()
            self.leito_done.wait()
        else:
            # pode ainda precisar de leito em casos raros (simulação)
            if random.random() < 0.05:
                leito_thread = threading.Thread(target=self.thread_leito, name=f"Leito-{self.pid}")
                leito_thread.start()
                self.leito_done.wait()


    def thread_consulta(self):
        log(f"Paciente {self.pid}: aguardando médico para consulta")
        acquired = medicos_sem.acquire(timeout=30)  # timeout alto para não bloquear indefinidamente
        if not acquired:
            log(f"Paciente {self.pid}: tempo de espera por médico excedido na consulta")
            self.consulta_done.set()
            return
        try:
            log(f"Paciente {self.pid}: em consulta (médico alocado)")
            dur = random.uniform(TEMPO_CONSULTA_MIN, TEMPO_CONSULTA_MAX)
            time.sleep(dur)
            log(f"Paciente {self.pid}: consulta finalizada (duração {dur:.2f}s)")
        finally:
            medicos_sem.release()
            self.consulta_done.set()

    def thread_exame(self):
        # Exames podem ou não precisar de médico (simulamos que alguns não)
        precisa_medico = random.random() < 0.3
        if precisa_medico:
            log(f"Paciente {self.pid}: aguardando médico para exame")
            acquired = medicos_sem.acquire(timeout=30)
            if not acquired:
                log(f"Paciente {self.pid}: tempo de espera por médico excedido no exame")
                self.exames_done.set()
                return
            try:
                log(f"Paciente {self.pid}: realizando exame com médico")
                dur = random.uniform(TEMPO_EXAME_MIN, TEMPO_EXAME_MAX)
                time.sleep(dur)
                log(f"Paciente {self.pid}: exame com médico finalizado ({dur:.2f}s)")
            finally:
                medicos_sem.release()
                self.exames_done.set()
        else:
            log(f"Paciente {self.pid}: realizando exame (sem médico necessário)")
            dur = random.uniform(TEMPO_EXAME_MIN, TEMPO_EXAME_MAX)
            time.sleep(dur)
            log(f"Paciente {self.pid}: exame finalizado ({dur:.2f}s)")
            self.exames_done.set()

    def thread_cirurgia(self):
        # precisa de sala e médico. Para evitar starvation/deadlock, adquira sempre na ordem:
        # 1) salas_sem, 2) medicos_sem  (todas as threads seguem mesma ordem)
        log(f"Paciente {self.pid}: aguardando sala de cirurgia")
        sala_acquired = salas_sem.acquire(timeout=60)
        if not sala_acquired:
            log(f"Paciente {self.pid}: tempo de espera por sala de cirurgia excedido")
            self.cirurgia_done.set()
            return
        try:
            log(f"Paciente {self.pid}: sala de cirurgia alocada, aguardando médico")
            medico_acquired = medicos_sem.acquire(timeout=60)
            if not medico_acquired:
                log(f"Paciente {self.pid}: não conseguiu médico após alocar sala (liberando sala)")
                return  # sala será liberada no finally
            try:
                log(f"Paciente {self.pid}: cirurgia iniciada (sala+medico alocados)")
                dur = random.uniform(TEMPO_CIRURGIA_MIN, TEMPO_CIRURGIA_MAX)
                time.sleep(dur)
                log(f"Paciente {self.pid}: cirurgia finalizada ({dur:.2f}s)")
            finally:
                medicos_sem.release()
                self.cirurgia_done.set()
        finally:
            salas_sem.release()

    def thread_leito(self):
        log(f"Paciente {self.pid}: aguardando leito")
        acquired = leitos_sem.acquire(timeout=120)
        if not acquired:
            log(f"Paciente {self.pid}: tempo de espera por leito excedido (alta sem leito!)")
            self.leito_done.set()
            return
        try:
            log(f"Paciente {self.pid}: leito alocado")
            # opcionalmente, leito pode requerer acompanhamento médico por um curto período
            precisa_medico = random.random() < 0.2
            if precisa_medico:
                log(f"Paciente {self.pid}: aguardando médico para acompanhar no leito")
                acquired_med = medicos_sem.acquire(timeout=60)
                if acquired_med:
                    try:
                        dur_med = random.uniform(0.5, 1.5)
                        time.sleep(dur_med)
                        log(f"Paciente {self.pid}: médico acompanhou no leito ({dur_med:.2f}s)")
                    finally:
                        medicos_sem.release()
                else:
                    log(f"Paciente {self.pid}: não veio médico para acompanhar no leito")
            # permanece no leito por algum tempo
            dur_leito = random.uniform(TEMPO_LEITO_MIN, TEMPO_LEITO_MAX)
            time.sleep(dur_leito)
            log(f"Paciente {self.pid}: alta do leito após {dur_leito:.2f}s")
        finally:
            leitos_sem.release()
            self.leito_done.set()

# -------------------------
# Simulação
# -------------------------
def run_simulation(n_patientes=N_PACIENTES):
    log(f"=== INICIANDO SIMULAÇÃO DO HOSPITAL ===")
    log(f"Recursos disponíveis:")
    log(f"- {N_MEDICOS} médicos para atendimento")
    log(f"- {N_SALAS_CIRURGIA} salas de cirurgia")
    log(f"- {N_LEITOS} leitos para internação")
    log(f"Total de {N_PACIENTES} pacientes aguardando atendimento")
    log("=======================================")
    
    patients = [Patient(i+1) for i in range(n_patientes)]
    threads = [p.start() for p in patients]
    
    log(">>> Todos os pacientes foram registrados e aguardam atendimento")

    # aguardando todos pacientes terminarem (join das threads que executam o processo)
    for t in threads:
        t.join()

    log("=== SIMULAÇÃO CONCLUÍDA ===")
    log("Todos os pacientes foram atendidos e liberados")
    log("=======================================")

if __name__ == "__main__":
    random.seed(42)
    run_simulation()
