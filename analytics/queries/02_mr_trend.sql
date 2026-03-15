SELECT
  CAST(played_at AS DATE) AS "日付",
  MAX(my_mr) AS "MR"
FROM v_battle_analytics
WHERE 1=1
  AND my_mr <= 2500
  [[AND {{my_name}}]]
  [[AND {{my_use_char}}]]
GROUP BY 1
ORDER BY 1 ASC

-- memo
-- ビジュアライゼーション : 線