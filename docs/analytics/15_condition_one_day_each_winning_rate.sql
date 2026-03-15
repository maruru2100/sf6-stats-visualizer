SELECT
  CAST(played_at AS DATE) AS "日付",
  COUNT(*) AS "試合数",
  ROUND(
    (SUM(is_win)::NUMERIC / COUNT(*)) * 100, 1
  ) AS "その日の勝率(%)"
FROM v_battle_analytics
WHERE 1=1
  -- プレイヤー名のみ連動
  [[AND {{my_name}}]]
GROUP BY 1
ORDER BY 1 ASC

-- memo
-- ビジュアライゼーション : 範囲
-- x軸 : 日付