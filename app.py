import streamlit as st
from notion_client import Client
import os
import time
import re
from datetime import datetime
from dotenv import load_dotenv
import tempfile
import pandas as pd # pandasをインポート
# import openpyxl # openpyxlはpandasが依存するため、直接インポートは不要だが、明示したい場合は記述

# .envファイルから環境変数を読み込む
load_dotenv()

st.title("Notionデータベース操作ツール")

# 環境変数から認証情報を読み込む
notion_token = os.getenv("NOTION_INTEGRATION_TOKEN")
existing_database_id = os.getenv("EXISTING_DATABASE_ID")

# サイドバーの設定
with st.sidebar:
    st.header("認証設定")
    if not notion_token:
        st.warning("Notion Integration Token が環境変数に設定されていません。")
    else:
        st.success("Notion Integration Token が設定されています。")

    st.divider()
    st.header("データベース設定")
    db_name = st.text_input("新規作成時のデータベース名", "タスク管理DB")
    
    # 親ページURLの入力欄 (新規データベース作成時のみ使用)
    parent_page_url = st.text_input(
        "親ページURL (新規データベース作成時のみ使用)",
        help="データベースを作成したいNotionのページのURLを貼り付けてください。既存データベースに追加する場合は不要です。"
    )

    st.divider()
    # ★変更: ファイルアップロードをExcel形式 (.xlsx) に変更
    uploaded_file = st.file_uploader("Excelファイル (.xlsx) をアップロード", type=["xlsx"]) # CSVも許容するなら ["xlsx", "csv"]

    st.info("認証情報は環境変数から読み込まれます。")
    if existing_database_id:
        st.info(f"既存データベースID (初期設定): {existing_database_id}")
    else:
        st.info("既存データベースIDは設定されていません。")


# NotionのURLからページIDを抽出する関数
def extract_page_id_from_url(url):
    match = re.search(r'([0-9a-f]{32})', url)
    if match:
        return match.group(1)
    match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', url)
    if match:
        return match.group(1).replace('-', '')
    return None

# 新規データベース作成関数
def create_database(notion, page_id, name):
    properties = {
        "名前": {"title": {}},
        "作業順": {"multi_select": {}},
        "対応": {"select": {}},
        "担当": {"multi_select": {}},
        "csv": {"rich_text": {}} # CSV→Excelに変わってもプロパティ名は「csv」のままでOK
    }
    
    try:
        new_db = notion.databases.create(
            parent={"page_id": page_id, "type": "page_id"},
            title=[{"type": "text", "text": {"content": name}}],
            properties=properties
        )
        st.success(f"データベース作成成功! ID: {new_db['id']}")
        return new_db["id"]
    except Exception as e:
        st.error(f"データベース作成エラー: {e}")
        return None

# 行の追加関数 (Excelファイルを読み込むように変更)
def add_rows_to_db(notion, db_id, excel_file_path): # 引数名をcsv_pathからexcel_file_pathに変更
    # ファイルの存在チェック
    if not os.path.exists(excel_file_path):
        st.error(f"指定されたExcelファイルが見つかりません: {excel_file_path}")
        return

    st.write(f"Excelファイル '{os.path.basename(excel_file_path)}' からデータを読み込み中...")

    df = None
    try:
        # ★変更: pandas.read_excel を使用してExcelファイルを読み込む
        df = pd.read_excel(excel_file_path)
        st.success("Excelファイルを正常に読み込みました。")
    except Exception as e:
        st.error(f"Excelファイルの読み込み中にエラーが発生しました: {e}")
        st.error("ファイルが正しいExcel形式 (.xlsx) であるか、および破損していないか確認してください。")
        return

    # DataFrameのヘッダー（カラム名）を取得
    excel_headers = df.columns.tolist()
    
    required_headers = ["名前", "作業順", "対応", "担当"] 
    
    missing_headers = [header for header in required_headers if header not in excel_headers]
    if missing_headers:
        st.error(f"Excelファイルに以下の必須ヘッダーが見つかりません: {', '.join(missing_headers)}。Notionデータベースのプロパティ名とExcelのヘッダーが完全に一致していることを確認してください。")
        return

    # DataFrameの各行をイテレートしてNotionにデータを追加
    for i, row_series in df.iterrows(): # i は行番号、row_series はその行のデータ (Series形式)
        row = row_series.to_dict() # Seriesを辞書に変換してアクセスしやすくする
        try:
            properties = {
                "名前": {"title": [{"text": {"content": str(row["名前"])}}]}, # Excelから読み込んだ値はstr()で変換
                "作業順": {"multi_select": [{"name": tag.strip()} for tag in str(row["作業順"]).split(',') if tag.strip()]},
                "対応": {"select": {"name": str(row["対応"]).strip()}},
                "担当": {"multi_select": [{"name": tag.strip()} for tag in str(row["担当"]).split(',') if tag.strip()]},
            }

            # Dateカラムの処理
            if "Date" in excel_headers and pd.notna(row["Date"]): # NaN (欠損値) チェック
                csv_date_str = str(row["Date"]).strip() # Excelから読み込むとdatetimeオブジェクトの場合もあるのでstr()に変換
                try:
                    # pandasは日付をdatetimeオブジェクトで読み込むことが多いので、その対応も追加
                    if isinstance(row["Date"], datetime):
                        parsed_date = row["Date"]
                    else: # 文字列の場合はパースを試みる
                        parsed_date = datetime.strptime(csv_date_str, "%Y-%m-%d")
                    
                    properties["Date"] = {"date": {"start": parsed_date.isoformat().split('T')[0]}}
                except ValueError:
                    st.warning(f"行 {i+1}: Excelの'Date'カラム '{csv_date_str}' が無効なフォーマットです。Notionの日付は空欄になります。")
                    properties["Date"] = {"date": None}
                except TypeError: # datetimeオブジェクト以外の型が来た場合
                    st.warning(f"行 {i+1}: Excelの'Date'カラム '{row['Date']}' が予期せぬ型です。日付として処理できません。")
                    properties["Date"] = {"date": None}
            else:
                properties["Date"] = {"date": None} # Dateカラムがないか空の場合

            # Excelの「csv」項目をNotionの「csv」プロパティに設定
            if "csv" in excel_headers and pd.notna(row["csv"]) and str(row["csv"]).strip():
                properties["csv"] = {"rich_text": [{"text": {"content": str(row["csv"]).strip()}}]}
            else: 
                properties["csv"] = {"rich_text": []}

            # ページを作成し、そのページのIDを取得
            new_page = notion.pages.create(parent={"database_id": db_id}, properties=properties)
            
            page_id = new_page["id"] # 作成されたページのIDを取得

            # ページの本文にテキストを追加 (「説明」カラムの内容)
            if "説明" in excel_headers and pd.notna(row["説明"]) and str(row["説明"]).strip():
                description_text = str(row["説明"]).strip()
                try:
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=[
                            {
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [
                                        {
                                            "type": "text",
                                            "text": {
                                                "content": description_text
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    )
                except Exception as e:
                    st.warning(f"⚠️ 行 {i+1} のページ本文への説明追加に失敗: {e}")
            
            st.success(f"✅ 行 {i+1} のページを作成しました")
            time.sleep(0.3)  # APIレートリミット回避
        except KeyError as ke:
            st.error(f"❌ 行 {i+1} の追加に失敗: Excelファイルに '{ke}' カラムが見つかりません。Notionデータベースのプロパティ名とExcelのヘッダーが完全に一致しているか確認してください。")
            break
        except Exception as e:
            st.error(f"❌ 行 {i+1} の追加に失敗: {e}")
    st.success("✅ すべての処理が完了しました！")
    st.balloons()


# ボタンのロジック
if st.button("データベースにデータを追加/作成") and notion_token:
    if uploaded_file is None:
        st.error("Excelファイルをアップロードしてください。")
        st.stop()

    # アップロードされたファイルを一時ファイルとして保存
    # ★変更: .xlsx の場合は suffix=".xlsx" にする
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file: 
        tmp_file.write(uploaded_file.getvalue())
        excel_file_path = tmp_file.name # 一時ファイルのパスを取得

    notion = Client(auth=notion_token)
    
    target_db_id = None
    
    if existing_database_id:
        target_db_id = existing_database_id
        st.info(f"環境変数の既存データベースID ({target_db_id}) を使用します。")
    
    if target_db_id:
        st.write(f"既存のデータベース (ID: {target_db_id}) にデータを追加します。")
        with st.spinner("処理中...\n(ページ本文にテキストを追加するため、通常より時間がかかる場合があります)"):
            add_rows_to_db(notion, target_db_id, excel_file_path) 
            db_link = f"https://notion.so/{target_db_id.replace('-', '')}"
            st.markdown(f"[データが追加されたデータベースを開く]({db_link})")
    else:
        if parent_page_url:
            parent_page_id = extract_page_id_from_url(parent_page_url)
            if parent_page_id:
                st.write(f"親ページ (ID: {parent_page_id}) の下に新しいデータベースを作成します。")
                with st.spinner("処理中...\n(ページ本文にテキストを追加するため、通常より時間がかかる場合があります)"):
                    db_id = create_database(notion, parent_page_id, db_name)
                    
                    if db_id:
                        add_rows_to_db(notion, db_id, excel_file_path)
                        db_link = f"https://notion.so/{db_id.replace('-', '')}"
                        st.markdown(f"[作成されたデータベースを開く]({db_link})")
            else:
                st.error("入力された親ページURLから有効なページIDを抽出できませんでした。URLが正しいか確認してください。")
        else:
            st.error("データを追加または新規作成するには、既存データベースIDが設定されているか、または親ページURLの入力が必要です。")
    
    # 一時ファイルを削除
    if os.path.exists(excel_file_path):
        os.remove(excel_file_path)
