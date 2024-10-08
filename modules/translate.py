import aiohttp
import asyncio
from config import *
from modules.pdf_edit import *

async def translate_str_data(key: str,text: str, target_lang: str,api_url:str) -> str:
    """
    DeepL APIを使用して、入力されたテキストを指定の言語に翻訳する非同期関数。
    タグハンドリングがXML向けになっているので注意

    Args:
        text (str): 翻訳するテキスト。
        target_lang (str): 翻訳先の言語コード（例: "EN", "JA", "FR"など）。

    Returns:
        str: 翻訳されたテキスト。

    Raises:
        Exception: APIリクエストが失敗した場合。
    """
    api_key = key  # 環境変数からDeepL APIキーを取得

    params = {
        "auth_key": api_key,           # DeepLの認証キー
        "text": text,                  # 翻訳するテキスト
        "target_lang": target_lang,    # 目的の言語コード
        'tag_handling': 'xml',         # タグの扱い
        "formality": "more"            # 丁寧な口調で翻訳
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, data=params) as response:
            if response.status == 200:
                result = await response.json()
                result = result["translations"][0]["text"]
                #print(F"Translate :{result}")
                return {'ok':True,'data':result}
            else:
                return {'ok':False,'message':f"DeepL API request failed with status code {response.status}"}

async def translate_blocks(blocks,key: str, target_lang: str,api_url:str):
    # テキスト検出
    translate_text = ""
    for page in blocks:
        for block in page:
            translate_text += block["text"] + "\n"
    
    # 翻訳
    translated_text = await translate_str_data(key,translate_text,target_lang,api_url)

    if translated_text['ok']:
        translated_text = translated_text['data']
    else:
        raise Exception(translated_text['message'])
    translated_text = translated_text.split('\n')
    
    # 翻訳後テキスト挿入
    for page in blocks:
        for block in page:
            block["text"] = translated_text.pop(0)

    return blocks

async def preprocess_translation_blocks(blocks,end_maker=(".",":",";"),end_maker_enable=True):
    """
    blockの文字列について、end makerがない場合、一括で翻訳できるように変換します。
    変換結果のblockを返します
    """
    results = []

    text = ""
    coordinates = []
    block_no = []
    page_no = []
    font_size = []

    for page in blocks:
        page_results = []
        temp_block_no = 0
        for block in page:
            text += " "+block["text"]
            page_no.append(block["page_no"])
            coordinates.append(block["coordinates"])
            block_no.append(block["block_no"])
            font_size.append(block["size"])

            if text.endswith(end_maker) or block["block_no"] - temp_block_no <= 1 or end_maker_enable == False:
                #マーカーがある場合格納
                page_results.append({"page_no":page_no,
                                     "block_no":block_no,
                                     "coordinates":coordinates,
                                     "text":text,
                                     "size":font_size})
                text = ""
                coordinates = []
                block_no = []
                page_no = []
                font_size = []
            temp_block_no = block["block_no"]
                
        results.append(page_results)
    return results
    
async def deepl_convert_xml_calc_cost(json_data):
    """
    翻訳コストを算出します。
    """
    cost =0
    price_per_character = 0.0025  # 1文字あたりの料金(円)
    xml_output = ""
    for page in json_data:
        for block in page:
            text = block['text']
            # 翻訳にて問題になる文字列を変換
            #text = text.replace('\n', '')

            xml_output += f"<div>{text}</div>\n"
    return xml_output,cost

async def pdf_translate(key,pdf_data,source_lang = 'en',to_lang = 'ja',api_url="https://api.deepl.com/v2/translate",debug = False,disable_translate=False):

    block_info = await extract_text_coordinates_dict(pdf_data)
    
    if debug:
        text_blocks,fig_blocks,remove_info,plot_images = await remove_blocks(block_info,10,lang=source_lang,debug=True)
    else:
        text_blocks,fig_blocks,_,_ = await remove_blocks(block_info,10,lang=source_lang)
    # 翻訳部分を消去したPDFデータを制作
    removed_textbox_pdf_data = await remove_textbox_for_pdf(pdf_data,text_blocks)
    removed_textbox_pdf_data = await remove_textbox_for_pdf(removed_textbox_pdf_data,fig_blocks)
    print("1.Generate removed_textbox_pdf_data")

    # 翻訳前のブロック準備
    preprocess_text_blocks = await preprocess_translation_blocks(text_blocks,(".",":",";"),True)
    preprocess_fig_blocks = await preprocess_translation_blocks(fig_blocks,(".",":",";"),False)
    print("2.Generate Prepress_blocks")

    # 翻訳実施
    if disable_translate is False:
        translate_text_blocks = await translate_blocks(preprocess_text_blocks,key,to_lang,api_url)
        translate_fig_blocks = await translate_blocks(preprocess_fig_blocks,key,to_lang,api_url)
        print("3.translated blocks")
        # pdf書き込みデータ作成
        write_text_blocks = await preprocess_write_blocks(translate_text_blocks,to_lang)
        write_fig_blocks = await preprocess_write_blocks(translate_fig_blocks,to_lang)
        print("4.Generate wirte Blocks")
        # pdfの作成
        if write_text_blocks != []:
            translated_pdf_data = await write_pdf_text(removed_textbox_pdf_data,write_text_blocks,to_lang)
        if write_fig_blocks != []:
            translated_pdf_data = await write_pdf_text(translated_pdf_data,write_fig_blocks,to_lang)
        translated_pdf_data = await write_logo_data(translated_pdf_data)
    else:
        print("99.Translate is False")
    
    """
    if debug:
        import json
        raw_blocks = await extract_text_coordinates_dict_dev(pdf_data)
        with open(Debug_folder_path+'raw_blocks.json', 'w', encoding='utf-8') as json_file:
            json.dump(raw_blocks, json_file, ensure_ascii=False, indent=2)
        with open(Debug_folder_path+'all_blocks.json', 'w', encoding='utf-8') as json_file:
            json.dump(block_info, json_file, ensure_ascii=False, indent=2)
        with open(Debug_folder_path+'text_block.json', 'w', encoding='utf-8') as json_file:
            json.dump(text_blocks, json_file, ensure_ascii=False, indent=2)
        with open(Debug_folder_path+'fig_blocks.json', 'w', encoding='utf-8') as json_file:
            json.dump(fig_blocks, json_file, ensure_ascii=False, indent=2)
        with open(Debug_folder_path+'remove_info.json', 'w', encoding='utf-8') as json_file:
            json.dump(remove_info, json_file, ensure_ascii=False, indent=2)
        
        if disable_translate is False:
            with open(Debug_folder_path+'translate_text_blocks.json', 'w', encoding='utf-8') as json_file:
                json.dump(translate_text_blocks, json_file, ensure_ascii=False, indent=2)
            with open(Debug_folder_path+'translate_fig_blocks.json', 'w', encoding='utf-8') as json_file:
                json.dump(translate_fig_blocks, json_file, ensure_ascii=False, indent=2)
            with open(Debug_folder_path+'write_text_blocks.json', 'w', encoding='utf-8') as json_file:
                json.dump(write_text_blocks, json_file, ensure_ascii=False, indent=2)
            with open(Debug_folder_path+'write_fig_blocks.json', 'w', encoding='utf-8') as json_file:
                json.dump(write_fig_blocks, json_file, ensure_ascii=False, indent=2)
    
        
        text_block_pdf_data = await pdf_draw_blocks(pdf_data,text_blocks,width=0,fill_opacity=0.3,fill_colorRGB=[0,0,1])
        fig_block_pdf_data = await pdf_draw_blocks(text_block_pdf_data,fig_blocks,width=0,fill_opacity=0.3,fill_colorRGB=[0,1,0])
        all_block_pdf_data = await pdf_draw_blocks(fig_block_pdf_data,remove_info,width=0,fill_opacity=0.7,fill_colorRGB=[1,0,0])
        
        # グラフの描画
        for image in plot_images:
            all_block_pdf_data = await write_image_data(all_block_pdf_data,image,(10,10,410,410))
            
        with open(Debug_folder_path+"show_blocks.pdf", "wb") as f:
            f.write(all_block_pdf_data)
        with open(Debug_folder_path+"removed_pdf.pdf", "wb") as f:
            f.write(removed_textbox_pdf_data)
        
        # block 消去理由を描画
        if disable_translate is False:
            translated_pdf_data = await write_pdf_text(translated_pdf_data,remove_info,text_color=[0,0,1],font_path="fonts/ariblk.ttf")
        else:
            translated_pdf_data = await write_pdf_text(all_block_pdf_data,remove_info,text_color=[0,0,1],font_path="fonts/ariblk.ttf")
        return translated_pdf_data
        """
    
    # 見開き結合の実施
    marged_pdf_data = await create_viewing_pdf(pdf_data,translated_pdf_data)
    print("5.Generate PDF Data")
    return marged_pdf_data

async def PDF_block_check(pdf_data,source_lang = 'en'):
    """
    ブロックの枠を作画します
    """

    block_info = await extract_text_coordinates_dict(pdf_data)

    text_blocks,fig_blocks,leave_blocks = await remove_blocks(block_info,10,lang=source_lang)
        
    text_block_pdf_data = await pdf_draw_blocks(pdf_data,text_blocks,width=0,fill_opacity=0.3,fill_colorRGB=[0,0,1])
    fig_block_pdf_data = await pdf_draw_blocks(text_block_pdf_data,fig_blocks,width=0,fill_opacity=0.3,fill_colorRGB=[0,1,0])
    all_block_pdf_data = await pdf_draw_blocks(fig_block_pdf_data,leave_blocks,width=0,fill_opacity=0.3,fill_colorRGB=[1,0,0])

    return all_block_pdf_data