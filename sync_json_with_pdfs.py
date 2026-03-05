import json
import logging
from pathlib import Path
from parser_fatura import parsear_fatura

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Sincronização automática

def sync():
    json_path = Path("dados_faturas.json")
    if not json_path.exists():
        logger.error("Arquivo dados_faturas.json não encontrado.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    faturas_dir = Path("faturas")
    if not faturas_dir.exists():
        logger.error("Diretório faturas/ não encontrado.")
        return

    novas_sincronizadas = 0

    for uc_dir in faturas_dir.iterdir():
        if not uc_dir.is_dir(): continue
        uc_code = uc_dir.name
        
        if uc_code not in data["unidades"]:
            logger.warning(f"UC {uc_code} não encontrada no JSON. Pulando.")
            continue

        unidade_data = data["unidades"][uc_code]
        faturas_existentes = {f["referencia"]: f for f in unidade_data["faturas"]}

        for pdf_file in uc_dir.glob("*.pdf"):
            ref = pdf_file.stem # ex: "2026-01"
            logger.info(f"Sincronizando: UC {uc_code} - {ref}")
            
            try:
                # O PDF agora dita 100% o resultado
                dados_pdf = parsear_fatura(str(pdf_file))
                dados_pdf["fonte"] = "extraido+pdf"

                fatura_obj = faturas_existentes.get(ref)
                if fatura_obj:
                    # Atualiza mantendo dados que não vêm do PDF (caso existam)
                    fatura_obj.update(dados_pdf)
                else:
                    # Adiciona nova fatura se não existia
                    nova_fatura = {
                        "mes": f"{ref[5:]}/{ref[:4]}",
                        "referencia": ref,
                        "pdf_path": str(pdf_file),
                        **dados_pdf
                    }
                    unidade_data["faturas"].append(nova_fatura)
                    novas_sincronizadas += 1
            
            except Exception as e:
                logger.error(f"Erro ao processar {pdf_file}: {e}")

    # Ordenar as faturas por referência após a sincronização
    for uc in data["unidades"]:
        data["unidades"][uc]["faturas"].sort(key=lambda x: x["referencia"], reverse=True)

    # Salva os arquivos atualizados
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    public_json = Path("dashboard/public/dados_faturas.json")
    if public_json.parent.exists():
        with open(public_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Sincronizado com {public_json}")

    logger.info(f"Sucesso! Sincronização direta concluída. {novas_sincronizadas} novas faturas.")

if __name__ == "__main__":
    sync()
