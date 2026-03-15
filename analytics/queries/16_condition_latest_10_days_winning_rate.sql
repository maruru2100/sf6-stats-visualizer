SELECT
  CAST(played_at AS DATE) AS "日付",
  COUNT(*) AS "試合数",
  SUM(is_win) AS "勝ち数",
  ROUND((SUM(is_win)::NUMERIC / COUNT(*)) * 100, 1) AS "勝率(%)"
FROM v_battle_analytics
WHERE 1=1
  [[AND {{my_name}}]]
  AND played_at >= CURRENT_DATE - INTERVAL '10 days'
GROUP BY 1
ORDER BY 1 DESC

-- memo
-- ビジュアライゼーション : コンボ
-- x軸 : 日付