from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import json,re,requests
from modules.backblaze_api import upload_byte

from modules.arxiv_api import get_arxiv_info_async,download_arxiv_pdf
from modules.translate import pdf_translate

app = FastAPI(timeout=300)

origins = [
    "http://localhost:5173",
    'https://indqx-demo-front.onrender.com'
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, #cookie サポート
    allow_methods=["*"], 
    allow_headers=["*"], #ブラウザからアクセスできるようにするレスポンスヘッダーを示します
)

# --------------- Paper meta DB用処理 ---------------

async def process_translate_arxiv_pdf(key,target_lang, arxiv_id,api_url):
    try:
        # PDFをダウンロードしてバイトデータを取得
        pdf_data = await download_arxiv_pdf(arxiv_id)
        
        #翻訳処理
        translate_data = await pdf_translate(key,pdf_data,to_lang=target_lang,api_url=api_url)
        download_url = await upload_byte(translate_data, 'arxiv_pdf', F"{arxiv_id}_{target_lang}.pdf", content_type='application/pdf')

        return download_url
    
    except Exception as e:
        print(f"Error processing arxiv_id {arxiv_id}: {str(e)}")
        raise

def load_license_data():
    with open('data/license.json', 'r') as f:
        return json.load(f)

ALLOWED_LANGUAGES = ['en', 'ja']

class TranslateRequest(BaseModel):
    deepl_url: str = "https://api.deepl.com/v2/translate"
    deepl_key: str
    target_lang: str = "ja"

@app.post("/arxiv/translate/{arxiv_id}")
async def translate_paper_data(arxiv_id: str, request: TranslateRequest):
    """
    abstract およびPDF を日本語に翻訳します。
    - target_lang:ISO 639-1にて記載のこと
    """
    target_lang = request.target_lang
    deepl_key = request.deepl_key
    deepl_url = request.deepl_url
    # arxiv_idの形式をチェック
    if not re.match(r'^\d{4}\.\d{5}$', arxiv_id):
        raise HTTPException(status_code=400, detail="Invalid arxiv URL.")
    
    # DeepL APIキーの有効性をチェック
    headers = {"Authorization": f"DeepL-Auth-Key {deepl_key}"}
    test_response = requests.get(f"{deepl_url}/usage", headers=headers)
    if test_response.status_code == 403:
        raise HTTPException(status_code=400, detail="Invalid DeepL API Key.")
    elif test_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Error checking DeepL API key.")

    try:
        # 許可された言語のリストに target_lang が含まれているかを確認
        if target_lang.lower() not in ALLOWED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"Unsupported target language: {target_lang}. Allowed languages: {', '.join(ALLOWED_LANGUAGES)}")
        # ライセンスデータを読み込み
        license_data = load_license_data()
        # Arxiv_データを読み込み
        arxiv_info = await get_arxiv_info_async(arxiv_id)
        # 存在しないArxiv IDの場合エラー
        if arxiv_info=={'authors': []}:
            raise HTTPException(status_code=400, detail="Invalid arxiv URL.")
        
        paper_license = arxiv_info['license']

        license_ok = license_data.get(paper_license, {}).get("OK", False)

        if not license_ok:
            raise HTTPException(status_code=400, detail="License not permitted for translation")
        
        try:
            pdf_dl_url = await process_translate_arxiv_pdf(deepl_key,target_lang, arxiv_id,deepl_url)
            return pdf_dl_url
        
        except Exception as e:
            error_message = str(e)
            if "DeepL API request failed with status code" in error_message:
                if "403" in error_message:
                    raise HTTPException(status_code=400, detail="DeepL認証に失敗しました。APIキーと登録ステータスを確認してください。")
                raise HTTPException(status_code=400, detail=error_message)
            else:
                raise e
    
    except HTTPException as e:
        # HTTPExceptionはそのまま投げる
        raise e
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo_app:app", host="0.0.0.0", port=8001,reload=True)