import streamlit as st
from notion_client import Client
import os
import csv
import time
import re
from datetime import datetime
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

st.title("Notionデータベース操作ツール")

# 環境変数から認証情報とファイルパスを読み込む
notion_token = os.getenv("NOTION_INTEGRATION_TOKEN")
csv_file_path = os.getenv("CSV_FILE_PATH")
existing_database_id = os.getenv("EXISTING_DATABASE_ID") # 環境変数からのみ読み込む
client_database_id = os.getenv("CLIENT_DATABASE_ID") # リレーション先のクライアントデータベースID (新規DB作成時に必要)

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
    
    # リレーション先のクライアントページURLの入力欄
    client_relation_url_input = st.text_input(
        "リレーション先のクライアントページURL",
        help="インポートする全ての項目をリレーションさせたいNotionのクライアントページのURLを貼り付けてください。未入力の場合、リレーションは設定されません。",
        key="client_relation_url" # 一意のキーを設定
    )
    
    st.divider()
    st.info("認証情報とCSVファイルは環境変数から読み込まれます。")
    if csv_file_path:
        st.info(f"使用するCSVファイル: {csv_file_path}")
    else:
        st.warning("CSVファイルパスが環境変数に設定されていません。")
    
    if existing_database_id:
        st.info(f"既存データベースID (初期設定): {existing_database_id}")
    else:
        st.info("既存データベースIDは設定されていません。")

    # クライアントデータベースIDの表示 (新規作成時に必要)
    if client_database_id:
        st.info(f"リレーション定義用クライアントデータベースID: {client_database_id}\n(新規データベース作成時にリレーションプロパティを定義するのに使用されます)")
    else:
        st.warning("リレーション定義用クライアントデータベースIDが環境変数に設定されていません。新規データベース作成時にリレーションプロパティを含めることができません。")


# NotionのURLからページIDを抽出する関数
def extract_page_id_from_url(url):
    match = re.search(r'([0-9a-f]{32})', url)
    if match:
        return match.group(1)
    match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', url)
    if match:
        return match.group(1).replace('-', '')
    return None

# 新規データベース作成関数 (Client Name リレーションプロパティの定義は維持)
def create_database(notion, page_id, name):
    properties = {
        "名前": {"title": {}},
        "作業順": {"multi_select": {}},
        "対応": {"select": {}},
        "担当": {"multi_select": {}},
    }
    
    # client_database_idが設定されている場合のみリレーションプロパティを含める
    if client_database_id:
        properties["Client Name"] = { # Notionデータベース側のプロパティ名に合わせる
            "relation": {
                "database_id": client_database_id,
                "single_property": {}
            }
        }
    else:
        st.warning("ClientデータベースIDが設定されていないため、新規データベースに'Client Name'リレーションプロパティは追加されません。")


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

# 本文テキスト、およびアプリUIから取得したURLからのリレーション設定を追加 (アイコン処理を削除)
def add_rows_to_db(notion, db_id, csv_path, specific_client_page_id):
    # CSVファイルの存在チェック
    if not os.path.exists(csv_path):
        st.error(f"指定されたCSVファイルが見つかりません: {csv_path}")
        return

    st.write(f"CSVファイル '{csv_path}' からデータを読み込み中...")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        required_csv_headers = ["名前", "作業順", "対応", "担当"] 
        csv_headers = reader.fieldnames
        
        missing_headers = [header for header in required_csv_headers if header not in csv_headers]
        if missing_headers:
            st.error(f"CSVファイルに以下の必須ヘッダーが見つかりません: {', '.join(missing_headers)}。Notionデータベースのプロパティ名とCSVヘッダーが完全に一致していることを確認してください。")
            return

        for i, row in enumerate(reader):
            try:
                properties = {
                    "名前": {"title": [{"text": {"content": row["名前"]}}]},
                    "作業順": {"multi_select": [{"name": tag.strip()} for tag in row["作業順"].split(',') if tag.strip()]},
                    "対応": {"select": {"name": row["対応"].strip()}},
                    "担当": {"multi_select": [{"name": tag.strip()} for tag in row["担当"].split(',') if tag.strip()]},
                }

                # Dateカラムの処理 (変更なし)
                if "Date" in csv_headers and row["Date"].strip():
                    csv_date_str = row["Date"].strip()
                    try:
                        parsed_date = datetime.strptime(csv_date_str, "%Y-%m-%d")
                        properties["Date"] = {"date": {"start": parsed_date.isoformat().split('T')[0]}}
                    except ValueError:
                        st.warning(f"行 {i+1}: CSVの'Date'カラム '{csv_date_str}' が無効なフォーマットです。Notionの日付は空欄になります。")
                        properties["Date"] = {"date": None}

                # ★変更: アイコンの処理を完全に削除
                # page_icon = None
                # if "Icon" in csv_headers and row["Icon"].strip():
                #     icon_value = row["Icon"].strip()
                #     if len(icon_value) <= 4 and not icon_value.startswith("http"):
                #         page_icon = {"emoji": icon_value}
                #     elif icon_value.startswith("http://") or icon_value.startswith("https://"):
                #         page_icon = {"external": {"url": icon_value}}
                #     else:
                #         st.warning(f"行 {i+1}: 'Icon'カラム '{icon_value}' は無効なアイコン形式（絵文字またはURLではありません）。アイコンは設定されません。")

                # リレーションプロパティの処理 (アプリUIからのIDを使用)
                if specific_client_page_id:
                    properties["Client Name"] = {"relation": [{"id": specific_client_page_id}]}
                else:
                    properties["Client Name"] = {"relation": []}


                # ページを作成し、そのページのIDを取得 (iconパラメータを削除)
                # if page_icon: # 条件分岐も不要
                #     new_page = notion.pages.create(parent={"database_id": db_id}, properties=properties, icon=page_icon)
                # else:
                new_page = notion.pages.create(parent={"database_id": db_id}, properties=properties)
                
                page_id = new_page["id"] # 作成されたページのIDを取得

                # ページの本文にテキストを追加 (「説明」カラムの内容)
                if "説明" in csv_headers and row["説明"].strip():
                    description_text = row["説明"].strip()
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
                st.error(f"❌ 行 {i+1} の追加に失敗: CSVファイルに '{ke}' カラムが見つかりません。Notionデータベースのプロパティ名とCSVヘッダーが完全に一致しているか確認してください。")
                break
            except Exception as e:
                st.error(f"❌ 行 {i+1} の追加に失敗: {e}")
    st.success("✅ すべての処理が完了しました！")
    st.balloons()


# ボタンのロジック
if st.button("データベースにデータを追加/作成") and notion_token and csv_file_path:
    notion = Client(auth=notion_token)
    
    target_db_id = None
    
    # リレーション先のクライアントページURLからIDを抽出
    client_relation_page_id = None
    if client_relation_url_input:
        client_relation_page_id = extract_page_id_from_url(client_relation_url_input)
        if not client_relation_page_id:
            st.error("入力されたクライアントページURLから有効なページIDを抽出できませんでした。URLが正しいか確認してください。")
            st.stop() # 処理を中断

    if existing_database_id:
        target_db_id = existing_database_id
        st.info(f"環境変数の既存データベースID ({target_db_id}) を使用します。")
    
    if target_db_id:
        st.write(f"既存のデータベース (ID: {target_db_id}) にデータを追加します。")
        with st.spinner("処理中...\n(ページ本文にテキストを追加するため、通常より時間がかかる場合があります)"):
            add_rows_to_db(notion, target_db_id, csv_file_path, client_relation_page_id) 
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
                        add_rows_to_db(notion, db_id, csv_file_path, client_relation_page_id)
                        db_link = f"https://notion.so/{db_id.replace('-', '')}"
                        st.markdown(f"[作成されたデータベースを開く]({db_link})")
            else:
                st.error("入力された親ページURLから有効なページIDを抽出できませんでした。URLが正しいか確認してください。")
        else:
            st.error("データを追加または新規作成するには、既存データベースIDが設定されているか、または親ページURLの入力が必要です。")
