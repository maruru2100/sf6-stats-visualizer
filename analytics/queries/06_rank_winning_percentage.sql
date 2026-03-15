SELECT
  COUNT(*) AS "総試合数",
  SUM(is_win) AS "勝ち数",
  ROUND(
    (SUM(is_win)::NUMERIC / COUNT(*)) * 100, 1
  ) AS "全体勝率(%)"
FROM v_battle_analytics
WHERE 1=1
  -- プレイヤー名のみでフィルタリング
  [[AND {{my_name}}]]

-- memo
-- ビジュアライゼーション : 数値