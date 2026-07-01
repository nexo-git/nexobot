"""Lambda standalone: analiza conversaciones de nexobot con GPT-4o-mini y escribe el resultado a S3.

No depende del paquete src/ del bot — usa boto3 directo para poder empaquetarse
con un único requirement externo (openai).

Flujo:
  1. Scan de la tabla de conversaciones agrupando turnos por session_id
  2. Para cada sesión: arma el hilo completo y pide a GPT-4o-mini que clasifique
     intent / resolved / frustration_level / topics
  3. Escribe un JSON-lines a s3://{bucket}/raw/conversation_analysis/dt=<hoy>/analysis.json
"""

import json
import os
import time
from datetime import datetime, timezone

import boto3
from openai import OpenAI

_dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
_table = _dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])
_s3 = boto3.client("s3")
_BUCKET = os.environ["DATALAKE_BUCKET"]
_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

_CLASSIFICATION_PROMPT = """Analizá esta conversación entre un cliente y el bot de *nexo* (courier USA -> Costa Rica).
Devolvé SOLO un JSON con este formato exacto, sin texto adicional:
{{
  "intent": "cotizacion" | "soporte_casillero" | "estado_pedido" | "queja" | "otro",
  "resolved": true | false,
  "frustration_level": "low" | "medium" | "high",
  "topics": ["tema1", "tema2"]
}}

Conversación:
{conversation}
"""


def _list_all_sessions() -> dict[str, list[dict]]:
    """Escanea la tabla completa y agrupa los turnos (no METADATA) por session_id."""
    sessions: dict[str, list[dict]] = {}
    scan_kwargs: dict = {}
    while True:
        response = _table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            if item.get("sk") == "METADATA" or "role" not in item:
                continue
            sessions.setdefault(item["session_id"], []).append(item)
        if "LastEvaluatedKey" not in response:
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sessions


def _classify(conversation_text: str) -> dict:
    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": _CLASSIFICATION_PROMPT.format(conversation=conversation_text)}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:
        print(f"Error clasificando conversación: {exc}")
        return {"intent": "error", "resolved": False, "frustration_level": "unknown", "topics": []}


def handler(event, context):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sessions = _list_all_sessions()

    records = []
    for session_id, turns in sessions.items():
        turns.sort(key=lambda x: x["sk"])
        conversation_text = "\n".join(f"{t['role']}: {t['content']}" for t in turns)

        classification = _classify(conversation_text)

        try:
            last_activity = int(turns[-1]["sk"].split("#")[0])
        except (ValueError, IndexError):
            last_activity = 0

        records.append({
            "session_id": session_id,
            "phone_number": session_id.removeprefix("whatsapp_"),
            "message_count": len(turns),
            "last_activity": last_activity,
            "analyzed_at": int(time.time()),
            "date": today,
            **classification,
        })

    key = f"raw/conversation_analysis/dt={today}/analysis.json"
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    _s3.put_object(Bucket=_BUCKET, Key=key, Body=body.encode("utf-8"))

    print(f"Analizadas {len(records)} conversaciones, escrito a s3://{_BUCKET}/{key}")
    return {"analyzed": len(records), "s3_key": key}
