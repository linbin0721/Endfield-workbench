from app.models import PuzzleCapability


PUZZLES = {
    "balloon": PuzzleCapability(
        id="balloon", name="浮空回收", recognition_available=True, solving_available=True,
        supported_rule_versions=["center-torque-v1"],
        rules_note="以棋盘几何中心为支点，升力按行列距离加权，左右与上下分别平衡；每格至多一个气球，使用全部库存",
    ),
    "circuit": PuzzleCapability(
        id="circuit", name="源石电路", recognition_available=False, solving_available=False,
        supported_rule_versions=[], rules_note="尚未开放",
    ),
}
