"""
geopandas.clip
==============

A module to clip vector data using GeoPandas.

"""
import warnings

import pandas as pd
from shapely.geometry import Polygon, MultiPolygon

from geopandas import GeoDataFrame, GeoSeries
from geopandas.array import _check_crs, _crs_mismatch_warn


_POINT_TYPES = ["Point", "MultiPoint"]
_LINE_TYPES = ["LineString", "MultiLineString", "LinearRing"]
_POLYGON_TYPES = ["Polygon", "MultiPolygon"]
_GEOMETRY_TYPES = [_POINT_TYPES, _LINE_TYPES, _POLYGON_TYPES]


def _clip_gdf_with_polygon(gdf, poly):
    """Clip geometry to the polygon extent.

    Clip an input GeoDataFrame to the polygon extent of the poly
    parameter.

    Parameters
    ----------
    gdf : GeoDataFrame, GeoSeries
        Dataframe to clip.

    poly : (Multi)Polygon
        Reference geometry used to spatially clip the data.

    Returns
    -------
    GeoDataFrame
        The returned GeoDataFrame is a subset of gdf that intersects
        with poly.
    """
    gdf_sub = gdf.iloc[gdf.sindex.query(poly, predicate="intersects")]

    # Clip the data with the polygon
    if isinstance(gdf_sub, GeoDataFrame):
        clipped = gdf_sub.copy()
        clipped[gdf.geometry.name] = gdf_sub.intersection(poly)
    else:
        # GeoSeries
        clipped = gdf_sub.intersection(poly)

    return clipped


def _validate_input_gdf(gdf):
    if not isinstance(gdf, (GeoDataFrame, GeoSeries)):
        raise TypeError(
            "'gdf' should be GeoDataFrame or GeoSeries, got {}".format(type(gdf))
        )


def _validate_input_mask(mask):
    if not isinstance(mask, (GeoDataFrame, GeoSeries, Polygon, MultiPolygon)):
        raise TypeError(
            "'mask' should be GeoDataFrame, GeoSeries or"
            "(Multi)Polygon, got {}".format(type(mask))
        )


def _validate_inputs(gdf, mask):
    _validate_input_gdf(gdf)
    _validate_input_mask(mask)
    _warn_if_crs_mismatch(gdf, mask)


def _warn_if_crs_mismatch(gdf, mask):
    if isinstance(mask, (GeoDataFrame, GeoSeries)):
        if not _check_crs(gdf, mask):
            _crs_mismatch_warn(gdf, mask, stacklevel=3)


def _contains_geometrycollection(gdf):
    return (gdf.geom_type == "GeometryCollection").any()


def _get_number_of_unique_geometry_types(gdf):
    return sum(gdf.geom_type.isin(geom_type).any() for geom_type in _GEOMETRY_TYPES)


def _keeping_geometry_type_is_possible(gdf):
    if _contains_geometrycollection(gdf):
        warnings.warn(
            "keep_geom_type can not be called on a GeoDataFrame with "
            "GeometryCollection."
        )
        return False
    number_of_unique_geometry_types = _get_number_of_unique_geometry_types(gdf)
    if number_of_unique_geometry_types > 1:
        warnings.warn("keep_geom_type can not be called on a mixed type GeoDataFrame.")
        return False
    return True


def _get_mask_bounding_box(mask):
    if isinstance(mask, (GeoDataFrame, GeoSeries)):
        box_mask = mask.total_bounds
    else:
        box_mask = mask.bounds
    return box_mask


def _input_bounding_boxes_intersect(gdf, mask):
    box_gdf = gdf.total_bounds
    box_mask = _get_mask_bounding_box(mask)
    x_overlaps = (box_mask[0] <= box_gdf[2]) and (box_gdf[0] <= box_mask[2])
    y_overlaps = (box_mask[1] <= box_gdf[3]) and (box_gdf[1] <= box_mask[3])
    return x_overlaps and y_overlaps


def _empty_from_gdf(gdf):
    return gdf.iloc[:0]


def _create_mask_polygon(mask):
    if isinstance(mask, (GeoDataFrame, GeoSeries)):
        poly = mask.geometry.unary_union
    else:
        poly = mask
    return poly


def _keep_only_original_geom_type(clipped_gdf, original_type):
    new_collections_were_created = (clipped_gdf.geom_type == "GeometryCollection").any()
    unique_geom_count_clipped = _get_number_of_unique_geometry_types(clipped_gdf)
    type_count_has_increased = unique_geom_count_clipped > 1
    if new_collections_were_created or type_count_has_increased:
        if new_collections_were_created:
            clipped_gdf = clipped_gdf.explode()

        if original_type in _LINE_TYPES:
            clipped_gdf = clipped_gdf.loc[clipped_gdf.geom_type.isin(_LINE_TYPES)]
        elif original_type in _POLYGON_TYPES:
            clipped_gdf = clipped_gdf.loc[clipped_gdf.geom_type.isin(_POLYGON_TYPES)]
    return clipped_gdf


def _recreate_initial_order(original_gdf, clipped_gdf):
    order = pd.Series(range(len(original_gdf)), index=original_gdf.index)
    if isinstance(clipped_gdf, GeoDataFrame):
        clipped_gdf["_order"] = order
        return clipped_gdf.sort_values(by="_order").drop(columns="_order")
    else:
        clipped_gdf = GeoDataFrame(geometry=clipped_gdf)
        clipped_gdf["_order"] = order
        return clipped_gdf.sort_values(by="_order").geometry


def clip(gdf, mask, keep_geom_type=False):
    """Clip points, lines, or polygon geometries to the mask extent.

    Both layers must be in the same Coordinate Reference System (CRS).
    The `gdf` will be clipped to the full extent of the clip object.

    If there are multiple polygons in mask, data from `gdf` will be
    clipped to the total boundary of all polygons in mask.

    Parameters
    ----------
    gdf : GeoDataFrame or GeoSeries
        Vector layer (point, line, polygon) to be clipped to mask.
    mask : GeoDataFrame, GeoSeries, (Multi)Polygon
        Polygon vector layer used to clip `gdf`.
        The mask's geometry is dissolved into one geometric feature
        and intersected with `gdf`.
    keep_geom_type : boolean, default False
        If True, return only geometries of original type in case of intersection
        resulting in multiple geometry types or GeometryCollections.
        If False, return all resulting geometries (potentially mixed-types).

    Returns
    -------
    GeoDataFrame or GeoSeries
         Vector data (points, lines, polygons) from `gdf` clipped to
         polygon boundary from mask.

    Examples
    --------
    Clip points (global cities) with a polygon (the South American continent):

    >>> world = geopandas.read_file(
    ...     geopandas.datasets.get_path('naturalearth_lowres'))
    >>> south_america = world[world['continent'] == "South America"]
    >>> capitals = geopandas.read_file(
    ...     geopandas.datasets.get_path('naturalearth_cities'))
    >>> capitals.shape
    (202, 2)

    >>> sa_capitals = geopandas.clip(capitals, south_america)
    >>> sa_capitals.shape
    (12, 2)
    """
    _validate_inputs(gdf, mask)
    if not _input_bounding_boxes_intersect(gdf, mask):
        return _empty_from_gdf(gdf)

    mask_polygon = _create_mask_polygon(mask)
    clipped_gdf = _clip_gdf_with_polygon(gdf, mask_polygon)
    if clipped_gdf.empty:
        return _empty_from_gdf(gdf)

    keeping_geometry_type_is_possible = (
        keep_geom_type and _keeping_geometry_type_is_possible(gdf)
    )
    if keeping_geometry_type_is_possible:
        clipped_gdf = _keep_only_original_geom_type(clipped_gdf, gdf.geom_type.iloc[0])

    return _recreate_initial_order(gdf, clipped_gdf)
