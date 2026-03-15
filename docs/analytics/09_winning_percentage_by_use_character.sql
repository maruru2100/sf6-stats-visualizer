SELECT
  my_char AS "使用キャラ",
  COUNT(*) AS "試合数",
  ROUND(
    (SUM(is_win)::NUMERIC / COUNT(*)) * 100, 1
  ) AS "勝率(%)"
FROM v_battle_analytics
WHERE 1=1
  -- プレイヤー名のみ連動
  [[AND {{my_name}}]]
GROUP BY 1
ORDER BY "勝率(%)" DESC

-- memo
-- ビジュアライゼーション : テーブル