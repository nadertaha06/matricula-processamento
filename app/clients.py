from urllib.parse import quote
import httpx
from app.config import get_settings


class ServicosAcademicos:
    def __init__(self, client=None):
        self.client = client or httpx.Client(timeout=5, trust_env=False)
        self.settings = get_settings()

    def solicitacao(self, sid):
        r = self.client.get(f'{self.settings.solicitacoes_url}/matriculas/{quote(sid, safe="")}')
        r.raise_for_status()
        return r.json()

    def turma(self, tid):
        r = self.client.get(f'{self.settings.disciplinas_url}/turmas/{quote(tid, safe="")}')
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def historico(self, aluno):
        r = self.client.get(f'{self.settings.solicitacoes_url}/alunos/{quote(aluno, safe="")}/historico')
        r.raise_for_status()
        return r.json()

    def reservar(self, candidato):
        tid = quote(candidato['turma_id'], safe='')
        r = self.client.post(f'{self.settings.disciplinas_url}/turmas/{tid}/reservas', json={
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
        r = self.client.delete(f'{self.settings.disciplinas_url}/turmas/{tid}/reservas/{sid}')
        if r.status_code != 404:
            r.raise_for_status()

    def close(self):
        self.client.close()
