-- ==========================================
-- 6. システム状態管理 (URL自動更新用)
-- ==========================================
CREATE TABLE IF NOT EXISTS system_status (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 初期データの投入
INSERT INTO system_status (key, value) VALUES ('public_url', 'Offline') ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE system_status IS 'システムの動作状態を管理するテーブル';
COMMENT ON COLUMN system_status.value IS '公開URLなどの設定値';
