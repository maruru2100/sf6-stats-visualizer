SELECT
  opponent_char AS "相手キャラ",
  COUNT(*) AS "総対戦数",
  ROUND(
    (SUM(is_win)::NUMERIC / COUNT(*)) * 100, 1
  ) AS "勝率(%)"
FROM v_battle_analytics
WHERE 1=1
  -- プレイヤー名のみ連動（自キャラでの絞り込みは行わない）
  [[AND {{my_name}}]]
GROUP BY 1
HAVING COUNT(*) >= 5
ORDER BY "勝率(%)" ASC
LIMIT 15

-- memo
-- ビジュアライゼーション : 詳細