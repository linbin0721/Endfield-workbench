from app.models import PuzzleCapability


PUZZLES = {
    "balloon": PuzzleCapability(
        id="balloon", name="浮空回收", recognition_available=True, solving_available=True,
        supported_rule_versions=["center-torque-v1"],
        rules_note="以棋盘几何中心为支点，升力按行列距离加权，左右与上下分别平衡；每格至多一个气球，使用全部库存",
    ),
    "circuit": PuzzleCapability(
        id="circuit", name="源石电路", recognition_available=True, solving_available=True,
        supported_rule_versions=["line-count-v1"],
        rules_note="按通道满足每行和每列的覆盖数；障碍格不可覆盖，固定格计入约束；全部库存拼块均可旋转且必须使用",
    ),
}
