def test_input_init():
    from gt_spector.input import Input
    inp = Input(":99")
    assert inp._display == ":99"
    assert inp._env == {"DISPLAY": ":99"}
