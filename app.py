import streamlit as st
from notion_client import Client
import os
import csv
import tempfile
from datetime import datetime
import time

st.title("Notionデータベース自動作成ツール")

# 認証情報入力
with st.sidebar:
    st.header("認証設定")
    notion_token = st.text_input("Notion Integration Token", type="password")
    parent_page_id = st.text_input("親ページID")
    
    st.divider()
    st.header("データベース設定")
    db_name = st.text_input("データベース名", "タスク管理DB")
    uploaded_file = st.file_uploader("CSVファイルをアップロード", type="csv")

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
        return new_db["id"]
    except Exception as e:
        st.error(f"データベース作成エラー: {e}")
        return None

def add_rows_to_db(notion, db_id, csv_path):
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                properties = {
                    "名前": {"title": [{"text": {"content": row["名前"]}}]},
                    "作業順": {"multi_select": [{"name": row["作業順"].strip()}]},
                    "対応": {"select": {"name": row["対応"].strip()}},
                    "担当": {"multi_select": [{"name": tag.strip()} for tag in row["担当"].split(',')]},
                    "説明": {"rich_text": [{"text": {"content": row["説明"]}}]}
                }
                notion.pages.create(parent={"database_id": db_id}, properties=properties)
                st.success(f"✅ 行 {i+1} を追加しました")
                time.sleep(0.3)  # APIレートリミット回避
            except Exception as e:
                st.error(f"❌ 行 {i+1} の追加に失敗: {e}")

if st.button("データベースを作成") and uploaded_file and notion_token and parent_page_id:
    notion = Client(auth=notion_token)
    
    # 一時ファイルにCSVを保存
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        csv_path = tmp_file.name
    
    with st.spinner("処理中..."):
        # データベース作成
        db_id = create_database(notion, parent_page_id, db_name)
        
        if db_id:
            st.success(f"データベース作成成功! ID: {db_id}")
            
            # データ追加
            add_rows_to_db(notion, db_id, csv_path)
            st.balloons()
            st.success("✅ すべての処理が完了しました！")
            
            # Notionのリンクを表示
            db_link = f"https://notion.so/{db_id.replace('-', '')}"
            st.markdown(f"[作成されたデータベースを開く]({db_link})")
