import streamlit as st
from notion_client import Client
import os
import csv
import time
import re # 追加
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

st.title("Notionデータベース操作ツール")

# 環境変数から認証情報とファイルパスを読み込む
notion_token = os.getenv("NOTION_INTEGRATION_TOKEN")
csv_file_path = os.getenv("CSV_FILE_PATH")
existing_database_id = os.getenv("EXISTING_DATABASE_ID")

# 親ページURLの入力欄を追加
with st.sidebar:
    st.header("認証設定")
    if not notion_token:
        st.warning("Notion Integration Token が環境変数に設定されていません。")
    else:
        st.success("Notion Integration Token が設定されています。")

    st.divider()
    st.header("データベース設定")
    db_name = st.text_input("新規作成時のデータベース名", "タスク管理DB") # 新規作成時の名残
    
    # 親ページURLの入力欄
    parent_page_url = st.text_input("親ページURL (新規データベース作成時のみ使用)", help="データベースを作成したいNotionのページのURLを貼り付けてください。")
    
    # 既存データベースIDの入力欄 (こちらは手動入力として残す)
    existing_database_id_input = st.text_input("既存データベースID (既存DBに追加する場合)", help="データを追加したいNotionデータベースのIDを直接入力してください。URLからIDを抽出することはできません。")
    
    st.divider()
    st.info("認証情報とCSVファイルは環境変数から読み込まれます。")
    if csv_file_path:
        st.info(f"使用するCSVファイル: {csv_file_path}")
    else:
        st.warning("CSVファイルパスが環境変数に設定されていません。")
    st.info(f"既存データベースID (環境変数): {existing_database_id if existing_database_id else '未設定'}")


# NotionのURLからページIDを抽出する関数
def extract_page_id_from_url(url):
    # NotionのページIDは32桁の16進数で、通常URLのパスの最後にハイフンなしで含まれる
    match = re.search(r'([0-9a-f]{32})', url)
    if match:
        return match.group(1)
    # または、より汎用的なID（ハイフンあり）も考慮
    match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', url)
    if match:
        return match.group(1).replace('-', '') # ハイフンを除去して返す
    return None # 見つからない場合はNoneを返す

# 新規データベース作成関数
def create_database(notion, page_id, name):
    properties = {
        "名前": {"title": {}},
        "作業順": {"multi_select": {}},
        "対応": {"select": {}},
        "担当": {"multi_select": {}},
        "説明": {"rich_text": {}}
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

def add_rows_to_db(notion, db_id, csv_path):
    # CSVファイルの存在チェック
    if not os.path.exists(csv_path):
        st.error(f"指定されたCSVファイルが見つかりません: {csv_path}")
        return

    st.write(f"CSVファイル '{csv_path}' からデータを読み込み中...")

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # CSVのヘッダーとNotionのプロパティの対応関係をチェックする
        # Notionのプロパティ名リストを取得 (API呼び出しで確認するのが理想だが、ここではコード上の定義で進める)
        # 例: database = notion.databases.retrieve(database_id=db_id)
        #     notion_property_names = [prop for prop in database['properties'].keys()]
        
        required_csv_headers = ["名前", "作業順", "対応", "担当", "説明"]
        csv_headers = reader.fieldnames
        
        missing_headers = [header for header in required_csv_headers if header not in csv_headers]
        if missing_headers:
            st.error(f"CSVファイルに以下の必須ヘッダーが見つかりません: {', '.join(missing_headers)}。Notionデータベースのプロパティ名とCSVヘッダーが完全に一致していることを確認してください。")
            return


        for i, row in enumerate(reader):
            try:
                properties = {
                    "名前": {"title": [{"text": {"content": row["名前"]}}]},
                    "作業順": {"multi_select": [{"name": tag.strip()} for tag in row["作業順"].split(',') if tag.strip()]}, # 空文字列のタグを避ける
                    "対応": {"select": {"name": row["対応"].strip()}},
                    "担当": {"multi_select": [{"name": tag.strip()} for tag in row["担当"].split(',') if tag.strip()]}, # 空文字列のタグを避ける
                    "説明": {"rich_text": [{"text": {"content": row["説明"]}}]}
                }
                notion.pages.create(parent={"database_id": db_id}, properties=properties)
                st.success(f"✅ 行 {i+1} を追加しました")
                time.sleep(0.3)  # APIレートリミット回避
            except KeyError as ke:
                st.error(f"❌ 行 {i+1} の追加に失敗: CSVファイルに '{ke}' カラムが見つかりません。Notionデータベースのプロパティ名とCSVヘッダーが一致しているか確認してください。")
                break # カラム名不一致の場合は処理を中断
            except Exception as e:
                st.error(f"❌ 行 {i+1} の追加に失敗: {e}")
    st.success("✅ すべての処理が完了しました！")
    st.balloons()


# ボタンのロジックを修正
if st.button("データベースにデータを追加/作成") and notion_token and csv_file_path: # ボタン名を修正
    notion = Client(auth=notion_token)
    
    target_db_id = None

    # 既存データベースID (手動入力) があればそれを使う
    if existing_database_id_input:
        target_db_id = existing_database_id_input
        st.info(f"入力された既存データベースID ({target_db_id}) を使用します。")
    # 環境変数の既存データベースIDがあればそれを使う (手動入力が優先)
    elif existing_database_id:
        target_db_id = existing_database_id
        st.info(f"環境変数の既存データベースID ({target_db_id}) を使用します。")

    if target_db_id:
        # 既存データベースにデータ追加
        st.write(f"既存のデータベース (ID: {target_db_id}) にデータを追加します。")
        with st.spinner("処理中..."):
            add_rows_to_db(notion, target_db_id, csv_file_path)
            # Notionのリンクを表示
            db_link = f"https://notion.so/{target_db_id.replace('-', '')}"
            st.markdown(f"[データが追加されたデータベースを開く]({db_link})")
    else:
        # 新規データベース作成の処理
        if parent_page_url:
            parent_page_id = extract_page_id_from_url(parent_page_url)
            if parent_page_id:
                st.write(f"親ページ (ID: {parent_page_id}) の下に新しいデータベースを作成します。")
                with st.spinner("処理中..."):
                    db_id = create_database(notion, parent_page_id, db_name)
                    
                    if db_id:
                        add_rows_to_db(notion, db_id, csv_file_path)
                        # Notionのリンクを表示
                        db_link = f"https://notion.so/{db_id.replace('-', '')}"
                        st.markdown(f"[作成されたデータベースを開く]({db_link})")
            else:
                st.error("入力された親ページURLから有効なページIDを抽出できませんでした。URLが正しいか確認してください。")
        else:
            st.error("データを追加または新規作成するには、既存データベースIDの入力、または親ページURLの入力が必要です。")
