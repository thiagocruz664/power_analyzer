import unittest
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QTabBar
from app.ui.main_window import MainWindow, DetachableTabBar


class TestTabs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_tabs_movable_property(self):
        window = MainWindow()
        self.assertTrue(window.tabs.isMovable())
        self.assertTrue(window.tabs.tabBar().isMovable())

    def test_tab_reordering(self):
        window = MainWindow()
        window._open_workspace("Medición en tiempo real")
        window._open_workspace("Registro")
        window._open_workspace("FFT")

        tb = window.tabs.tabBar()
        initial_tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        self.assertEqual(initial_tabs, ["Medición en tiempo real", "Registro", "FFT"])

        # Simular arrastrar la pestaña 'FFT' (índice 2) a la posición de la pestaña 0
        r2 = tb.tabRect(2)
        r0 = tb.tabRect(0)

        # Mouse press en FFT
        p_press = r2.center()
        ev_press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(p_press),
            QPointF(tb.mapToGlobal(p_press)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mousePressEvent(ev_press)

        # Mouse move a posición de Tab 0 (movimiento horizontal dentro de la barra)
        p_move = r0.center()
        ev_move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(p_move),
            QPointF(tb.mapToGlobal(p_move)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mouseMoveEvent(ev_move)

        # Mouse release
        ev_release = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(p_move),
            QPointF(tb.mapToGlobal(p_move)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mouseReleaseEvent(ev_release)

        reordered_tabs = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        self.assertEqual(reordered_tabs, ["FFT", "Medición en tiempo real", "Registro"])
        self.assertEqual(len(window.detached_windows), 0)

    def test_tab_detaching_and_restoring(self):
        window = MainWindow()
        window._open_workspace("Medición en tiempo real")
        window._open_workspace("Registro")
        window._open_workspace("FFT")

        tb = window.tabs.tabBar()
        self.assertEqual(window.tabs.count(), 3)

        # Arrastrar 'Registro' fuera de la barra (hacia abajo al espacio de trabajo)
        reg_idx = -1
        for i in range(window.tabs.count()):
            if window.tabs.tabText(i) == "Registro":
                reg_idx = i
                break
        self.assertGreaterEqual(reg_idx, 0)

        r_reg = tb.tabRect(reg_idx)
        p_start = r_reg.center()

        ev_press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(p_start),
            QPointF(tb.mapToGlobal(p_start)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mousePressEvent(ev_press)

        # Mover deliberadamente hacia abajo (+40px más allá de la barra)
        p_out = QPoint(p_start.x(), tb.height() + 40)
        ev_move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(p_out),
            QPointF(tb.mapToGlobal(p_out)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mouseMoveEvent(ev_move)

        ev_release = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(p_out),
            QPointF(tb.mapToGlobal(p_out)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mouseReleaseEvent(ev_release)

        # Verificar que se desprendió
        self.assertEqual(len(window.detached_windows), 1)
        self.assertEqual(window.tabs.count(), 2)
        self.assertNotIn("Registro", [window.tabs.tabText(i) for i in range(window.tabs.count())])

        # Cerrar la ventana desprendida para restaurar
        detached_window = list(window.detached_windows.values())[0]
        detached_window.close()

        self.assertEqual(len(window.detached_windows), 0)
        self.assertEqual(window.tabs.count(), 3)
        self.assertIn("Registro", [window.tabs.tabText(i) for i in range(window.tabs.count())])

    def test_close_button_click(self):
        window = MainWindow()
        window._open_workspace("Medición en tiempo real")
        window._open_workspace("Registro")
        window._open_workspace("FFT")

        tb = window.tabs.tabBar()
        self.assertEqual(window.tabs.count(), 3)

        # Clic en el botón de cerrar de la pestaña 1 ("Registro")
        close_btn = tb.tabButton(1, QTabBar.ButtonPosition.RightSide)
        self.assertIsNotNone(close_btn)
        close_btn.click()

        self.assertEqual(window.tabs.count(), 2)
        self.assertEqual(
            [window.tabs.tabText(i) for i in range(window.tabs.count())],
            ["Medición en tiempo real", "FFT"],
        )

    def test_close_button_click_does_not_detach(self):
        window = MainWindow()
        window._open_workspace("Medición en tiempo real")
        window._open_workspace("Registro")

        tb = window.tabs.tabBar()
        close_btn = tb.tabButton(1, QTabBar.ButtonPosition.RightSide)
        btn_center = close_btn.geometry().center()

        # Presionar sobre el botón de cerrar
        ev_press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(btn_center),
            QPointF(tb.mapToGlobal(btn_center)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tb.mousePressEvent(ev_press)

        # tb._drag_title debe ser None para no disparar arrastre
        self.assertIsNone(tb._drag_title)


if __name__ == "__main__":
    unittest.main()
