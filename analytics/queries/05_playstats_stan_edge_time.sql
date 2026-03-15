SELECT
    recorded_at AS "取得日",
    player_name AS "プレイヤー名",
	stun_win AS "スタンさせた回数",
	stun_lose AS "スタンさせられた回数",
	wall_push_sec AS "端に追い詰めた時間",
	wall_pushed_sec AS "端に追い詰められた時間"
FROM 
    player_stats
WHERE 
    [[ {{user_selection}} ]]
ORDER BY 
    recorded_at ASC;

-- memo
-- ビジュアライゼーション : 線
-- X軸 : 取得日