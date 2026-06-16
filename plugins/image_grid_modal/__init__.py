"""
Image Grid Modal Panel v1.15.0

Shows slices of the current group as a media grid (1–24 slices, variable
per group). Handles both image and video slices. A dropdown controls how
many slices to display.

Works only with grouped datasets.

| Copyright 2017-2026, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""

import urllib.parse

import fiftyone.operators as foo
import fiftyone.operators.types as types


def _media_url(filepath):
    """Returns a browser-accessible URL for the given filepath."""
    try:
        import fiftyone.core.storage as fos
        url = fos.get_url(filepath)
        if url != filepath:
            return url
    except Exception:
        pass
    return "/media?filepath=" + urllib.parse.quote(filepath, safe="")


def _load_slices(ctx):
    """Returns {name, url, media_type} dicts for all slices in the current group."""
    if not ctx.current_sample:
        return []
    dataset = ctx.dataset
    if dataset.media_type != "group":
        return []
    try:
        current = dataset[ctx.current_sample]
        group_id = current.group.id
        group = dataset.get_group(group_id)
        group_media_types = getattr(dataset, "group_media_types", {})
        return [
            {
                "name": slice_name,
                "url": _media_url(sample.filepath),
                "media_type": group_media_types.get(slice_name, "image"),
            }
            for slice_name, sample in sorted(group.items())
        ]
    except Exception:
        return []


def _n_cols(n):
    if n <= 0:
        return 1
    if n <= 3:
        return n
    if n <= 8:
        return 4
    if n <= 12:
        return 4
    return 6


class ImageGridPanel(foo.Panel):

    @property
    def config(self):
        return foo.PanelConfig(
            name="image_grid_modal",
            label="Group Image Grid",
            surfaces="modal",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_load(self, ctx):
        self._refresh(ctx)

    def on_change_current_sample(self, ctx):
        self._refresh(ctx)

    def on_change_group_slice(self, ctx):
        self._refresh(ctx)

    # ------------------------------------------------------------------
    # Event handlers — passed as callables to panel widgets
    # ------------------------------------------------------------------

    def _on_change_slice_selector(self, ctx):
        val = ctx.params.get("value")
        if val is not None:
            ctx.panel.state.display_count = max(1, min(24, int(float(val))))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh(self, ctx):
        dataset_name = ctx.dataset.name if ctx.dataset else None
        ctx.panel.state.dataset_name = dataset_name

        is_group = ctx.dataset.media_type == "group"
        ctx.panel.state.is_group = is_group

        # Always clear lists so stale data from a previous dataset is never shown.
        ctx.panel.state.all_urls = []
        ctx.panel.state.all_names = []
        ctx.panel.state.all_media_types = []
        ctx.panel.state.n_all = 0

        if not is_group:
            return

        slices = _load_slices(ctx)
        n_all = len(slices)

        ctx.panel.state.all_urls = [s["url"] for s in slices]
        ctx.panel.state.all_names = [s["name"] for s in slices]
        ctx.panel.state.all_media_types = [s["media_type"] for s in slices]
        ctx.panel.state.n_all = n_all

        initial = min(n_all, 24)
        ctx.panel.state.slice_selector = initial
        ctx.panel.state.display_count = initial

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, ctx):
        # Detect dataset switches — panel state persists across dataset navigation.
        current_dataset = ctx.dataset.name if ctx.dataset else None
        if current_dataset != ctx.panel.state.dataset_name:
            self._refresh(ctx)

        # Auto-initialize after hot-reload or state loss.
        if ctx.current_sample and not ctx.panel.state.n_all:
            self._refresh(ctx)

        panel = types.Object()

        is_group = ctx.panel.state.is_group or False
        n_all = ctx.panel.state.n_all or 0
        all_urls = ctx.panel.state.all_urls or []
        all_names = ctx.panel.state.all_names or []
        all_mts = ctx.panel.state.all_media_types or []

        if not is_group:
            panel.md("_This panel only works with grouped datasets._", name="status")
            return types.Property(panel, view=types.VStackView())

        if n_all == 0:
            panel.md("_Open a sample to view its group slices._", name="status")
            return types.Property(panel, view=types.VStackView())

        display_count = int(ctx.panel.state.display_count or min(n_all, 24))

        # Pass on_change as a callable — the naming-convention approach
        # (on_change_slice_selector as a method) does not work in this version.
        panel.enum(
            "slice_selector",
            values=list(range(1, n_all + 1)),
            label="Slices to show",
            view=types.DropdownView(),
            on_change=self._on_change_slice_selector,
        )

        displayed = list(zip(all_names, all_urls, all_mts))[:display_count]
        n = len(displayed)

        panel.md(
            f"_Showing {n} of {n_all} slice{'s' if n_all != 1 else ''}_",
            name="status",
        )

        cols = _n_cols(n)
        # Cell height budget: image portion + ~24 px for the label on top.
        img_h_map = {1: "280px", 2: "160px", 3: "130px", 4: "110px", 6: "85px"}
        img_height = img_h_map.get(cols, "90px")
        cell_height = f"{int(img_height[:-2]) + 24}px"

        width_pct = f"{100.0 / cols:.4f}%"

        # Each cell has an explicit fixed size (width% × cell_height px) with
        # overflow:hidden. This guarantees:
        #   - Equal widths: explicit % cannot be overridden by content or BFC.
        #   - No bleed: overflow:hidden clips the image at the cell boundary.
        # The row h_stack also carries height+overflow as a second constraint
        # in case the frontend treats the cell height as min-height.
        # Labels are placed first (top of cell) so they're always within the
        # visible area, with the image rendering below them.
        cell_style = {
            "width": width_pct,
            "minWidth": width_pct,
            "height": cell_height,
            "overflow": "hidden",
            "flexShrink": 0,
            "flexGrow": 0,
        }
        row_style = {"height": cell_height, "overflow": "hidden"}

        n_rows = (n + cols - 1) // cols
        for row_idx in range(n_rows):
            row = panel.h_stack(
                f"row_{display_count}_{row_idx}",
                gap=0,
                componentsProps={"style": row_style},
            )
            for col_idx in range(cols):
                item_idx = row_idx * cols + col_idx
                cell = row.v_stack(
                    f"cell_{display_count}_{item_idx}",
                    gap=0,
                    componentsProps={"style": cell_style},
                )
                if item_idx >= n:
                    cell.md("&nbsp;", name=f"sp_{display_count}_{item_idx}")
                    continue
                name, url, mt = displayed[item_idx]
                # Label first so it sits at the top of the clipped cell area.
                cell.md(f"**{name}**", name=f"lbl_{display_count}_{item_idx}")
                if mt == "video":
                    cell.media_player(
                        f"player_{display_count}_{item_idx}", url=url, height=img_height
                    )
                else:
                    cell.view(
                        f"img_{display_count}_{item_idx}",
                        types.ImageView(width="100%", height=img_height, alt=name),
                        default=url,
                    )

        return types.Property(panel, view=types.VStackView(gap=2))


def register(p):
    p.register(ImageGridPanel)
