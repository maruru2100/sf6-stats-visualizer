SELECT
    recorded_at AS "取得日",
    player_name AS "プレイヤー名",
	d_od_pct AS "OD使用率",
    d_parry_pct AS "パリィ使用率",
    d_impact_pct AS "インパクト使用率",
	d_reversal_pct AS "リバサインパクト使用率",
	d_rush_p_pct AS "生ラッシュ率",
    d_rush_c_pct AS "キャンセルラッシュ使用率"
FROM 
    player_stats
WHERE 
    [[ {{user_selection}} ]]
ORDER BY 
    recorded_at ASC;

-- memo
-- ビジュアライゼーション : 線
-- X軸 : 取得日