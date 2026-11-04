from buzz.db.dao.transcription_dao import TranscriptionDAO


def all_transcription_ids(transcription_dao: TranscriptionDAO) -> list[str]:
    query = transcription_dao._create_query()
    if not query.exec("SELECT id FROM transcription"):
        raise Exception(query.lastError().text())
    ids = []
    while query.next():
        ids.append(query.value("id"))
    return ids
