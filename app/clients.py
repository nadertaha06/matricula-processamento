import time
from urllib.parse import quote
import httpx
from prometheus_client import Counter, Histogram
from app.config import get_settings
from app.metrics import BUCKETS_HTTP

CHAMADAS_HTTP = Counter('chamadas_http_saida_total', 'Chamadas HTTP aos outros servicos por destino e status.',
    ('destino', 'status'))
DURACAO_CHAMADAS_HTTP = Histogram('chamadas_http_saida_duracao_seconds',
    'Duracao das chamadas HTTP aos outros servicos.', ('destino',), buckets=BUCKETS_HTTP)


class ServicosAcademicos:
    def __init__(self, client=None):
        self.client = client or httpx.Client(timeout=5, trust_env=False)
        self.settings = get_settings()
        self.client.headers['X-Service-Token'] = self.settings.internal_api_token

    def _chamar(self, destino, metodo, url, **kwargs):
        status = 'erro'  # no HTTP response: connection failure or timeout
        inicio = time.perf_counter()
        try:
            r = self.client.request(metodo, url, **kwargs)
            status = str(r.status_code)
            return r
        finally:
            DURACAO_CHAMADAS_HTTP.labels(destino=destino).observe(time.perf_counter() - inicio)
            CHAMADAS_HTTP.labels(destino=destino, status=status).inc()

    def solicitacao(self, sid):
        r = self._chamar('solicitacoes', 'GET', f'{self.settings.solicitacoes_url}/matriculas/{quote(sid, safe="")}')
        r.raise_for_status()
        return r.json()

    def turma(self, tid):
        r = self._chamar('disciplinas', 'GET', f'{self.settings.disciplinas_url}/turmas/{quote(tid, safe="")}')
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def historico(self, aluno):
        r = self._chamar('solicitacoes', 'GET', f'{self.settings.solicitacoes_url}/alunos/{quote(aluno, safe="")}/historico')
        r.raise_for_status()
        return r.json()

    def reservar(self, candidato):
        tid = quote(candidato['turma_id'], safe='')
        r = self._chamar('disciplinas', 'POST', f'{self.settings.disciplinas_url}/turmas/{tid}/reservas', json={
            'solicitacao_id':candidato['solicitacao_id'], 'aluno_id':candidato['aluno_id']})
        if r.status_code == 409:
            motivo = r.json()['detail']
            if motivo not in {'SEM_VAGAS','CHOQUE_HORARIO','DISCIPLINA_JA_MATRICULADA','RESERVA_CANCELADA'}:
                r.raise_for_status()
            return motivo
        r.raise_for_status()
        return None

    def liberar(self, candidato):
        tid = quote(candidato['turma_id'], safe='')
        sid = quote(candidato['solicitacao_id'], safe='')
        r = self._chamar('disciplinas', 'DELETE', f'{self.settings.disciplinas_url}/turmas/{tid}/reservas/{sid}')
        if r.status_code != 404:
            r.raise_for_status()

    def close(self):
        self.client.close()
