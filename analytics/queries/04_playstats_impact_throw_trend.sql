SELECT
    recorded_at AS "取得日",
    player_name AS "プレイヤー名",
	impact_win AS "インパクト成功回数",
	impact_pc_win AS "インパクトパニカン成功",
    impact_counter_win AS "インパクト返し成功回数",
    impact_lose AS "インパクト被弾回数",
	impact_counter_lose AS "インパクトカウンター被弾回数",
	impact_pc_lose AS "インパクトパニカン被弾回数",
	just_parry_count AS "ジャスパ回数",
	throw_win AS "投げ成功回数",
	throw_lose AS "投げられた回数",
	throw_escape AS "投げ抜け回数"
FROM 
    player_stats
WHERE 
    [[ {{user_selection}} ]]
ORDER BY 
    recorded_at DESC;

-- memo
-- ビジュアライゼーション : 線
-- X軸 : 取得日