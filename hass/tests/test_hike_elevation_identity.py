"""RF1830-10: an elevation answer is a profile only when every requested position has exactly one sample identity."""

import copy
import unittest

from hass import hike_lookup as hl
from hass.tests.test_hike_lookup import TODAY, NoNetwork, Synthetic, said, straight, way


def body(ids, values=None):
    values = values if values is not None else [100 + 10 * k for k in range(len(ids))]
    return {"samples": [{"locationId": i, "value": str(v)} for i, v in zip(ids, values)]}


class Identity(NoNetwork):
    def test_duplicate_ids_with_equal_count_do_not_form_a_profile(self):
        self.assertIsNone(hl.elevations_from(body([0, 0, 2]), 3))
        self.assertIsNone(hl.elevations_from(body([0, 0, 0]), 3))
        self.assertIsNone(hl.elevations_from(body([0, 0, 2], [5, 5, 5]), 3))
        self.assertIsNone(hl.elevations_from(body([0, 0, 1]), 2))

    def test_missing_negative_and_out_of_range_ids_are_not_renumbered(self):
        for ids in ([1, 2, 3], [3, 2, 1], [-1, 0, 1], [0, 1, 5], [0, 0, 2], [2, 0, 0]):
            self.assertIsNone(hl.elevations_from(body(ids), 3), ids)

    def test_ids_are_exact_integer_positions_not_lossy_coercions(self):
        for bad in (True, False, 0.0, 1.5, None, [0], {"a": 0}, "x", "-1", "+1", "1.0", "", " 1", "١", float("inf")):
            self.assertIsNone(hl.elevations_from(body([0, bad, 2]), 3), repr(bad))
        self.assertEqual(hl.elevations_from(body([0, "1", 2]), 3), [100.0, 110.0, 120.0])
        self.assertIsNone(hl.elevations_from(body([0, "0", 2]), 3))
        self.assertIsNone(hl.elevations_from(body([0, 1, "1"]), 3))

    def test_shuffled_complete_profile_is_restored_without_mutation(self):
        b = body([2, 0, 1], [120, 100, 110])
        before = copy.deepcopy(b)
        self.assertEqual(hl.elevations_from(b, 3), [100.0, 110.0, 120.0])
        self.assertEqual(b, before)
        self.assertIsNone(hl.elevations_from(body([0, 1, 2], [100, "NoData", 120]), 3))

    def test_bad_optional_profile_keeps_route_but_has_no_climb_number(self):
        class Dup(Synthetic):
            def get(self, service, request):
                if service == "elevation":
                    n = len(request["points"])
                    return hl.Response({"samples": [{"locationId": 0, "value": str(100 + 5 * i)} for i in range(n)]}, TODAY)
                return super().get(service, request)

        result = hl.lookup("Creek Walk", Dup([way(1, "Creek Walk", straight())]), today=TODAY)
        c = result.candidates[0]
        self.assertEqual((c.sure, c.gain_ft, c.miles, c.shape), (True, None, 0.9, "point-to-point"))
        self.assertIsNone(c.record["gain_ft"])
        self.assertIn("no climbing figure I trust", said(result))
        self.assertNotIn("feet of climbing", said(result))
        self.assertEqual(hl.route_add_args(c)["elevation"], "To be confirmed")

    def test_healthy_profile_still_gives_a_climb(self):
        c = hl.lookup("Creek Walk", Synthetic([way(1, "Creek Walk", straight())]), today=TODAY).candidates[0]
        self.assertIsNotNone(c.gain_ft)


if __name__ == "__main__":
    unittest.main()
