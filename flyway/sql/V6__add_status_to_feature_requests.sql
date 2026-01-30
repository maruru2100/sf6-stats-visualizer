-- 要望の状態を管理するカラムを追加（デフォルトは 'pending'）
ALTER TABLE feature_requests ADD COLUMN status VARCHAR(20) DEFAULT 'pending';

-- 管理者からの回答や却下理由を格納するカラムを追加
ALTER TABLE feature_requests ADD COLUMN admin_comment TEXT;

-- カラムにコメントを追加
COMMENT ON COLUMN feature_requests.status IS '要望のステータス（pending:受付中, rejected:却下, completed:完了）';
COMMENT ON COLUMN feature_requests.admin_comment IS '管理者からのフィードバックや却下理由';

-- ステータスでの絞り込みを高速化するためのインデックス
CREATE INDEX idx_feature_requests_status ON feature_requests (status);