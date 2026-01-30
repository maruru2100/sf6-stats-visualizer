-- テーブルが既に存在しない場合のみ作成（冪等性の担保）
CREATE TABLE IF NOT EXISTS feature_requests (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- テーブル全体へのコメント
COMMENT ON TABLE feature_requests IS 'Botユーザーからの匿名改善要望を管理するテーブル';

-- 各カラムへの詳細コメント
COMMENT ON COLUMN feature_requests.id IS '要望の一意識別ID（自動採番）';
COMMENT ON COLUMN feature_requests.content IS '要望の本文（ユーザーが入力したテキスト）';
COMMENT ON COLUMN feature_requests.created_at IS '要望が送信された日時（タイムゾーン付き）';

-- 運用上、最新の要望から順に取得することが多いため、作成日時に降順インデックスを貼る
CREATE INDEX IF NOT EXISTS idx_feature_requests_created_at ON feature_requests (created_at DESC);