SELECT
  opponent_char AS "相手キャラ",
  opponent_control AS "相手の操作",
  COUNT(*) AS "試合数",
  ROUND((SUM(is_win)::NUMERIC / COUNT(*)) * 100, 1) AS "勝率(%)"
FROM v_battle_analytics
WHERE 1=1
  [[AND {{my_name}}]]
  [[AND {{my_use_char}}]]
GROUP BY 1, 2
HAVING COUNT(*) >= 3
ORDER BY "勝率(%)" ASC

-- memo
-- ビジュアライゼーション : 詳細