import abc

from firedrake.preconditioners.base import PCBase
from firedrake.petsc import PETSc
from firedrake.ufl_expr import TestFunction, TrialFunction
from firedrake.dmhooks import get_function_space

__all__ = ("AssembledPC", "ExplicitSchurPC")


class AssembledPC(PCBase):
    """A matrix-free PC that assembles the operator.

    Internally this makes a PETSc PC object that can be controlled by
    options using the extra options prefix ``assembled_``.
    """

    _prefix = "assembled_"

    def initialize(self, pc):
        from firedrake.assemble import allocate_matrix, create_assembly_callable

        _, P = pc.getOperators()

        if pc.getType() != "python":
            raise ValueError("Expecting PC type python")
        opc = pc
        appctx = self.get_appctx(pc)
        fcp = appctx.get("form_compiler_parameters")

        V = get_function_space(pc.getDM())
        test = TestFunction(V)
        trial = TrialFunction(V)

        if P.type == "python":
            context = P.getPythonContext()
            # It only makes sense to preconditioner/invert a diagonal
            # block in general.  That's all we're going to allow.
            if not context.on_diag:
                raise ValueError("Only makes sense to invert diagonal block")

        prefix = pc.getOptionsPrefix()
        options_prefix = prefix + self._prefix

        mat_type = PETSc.Options().getString(options_prefix + "mat_type", "aij")

        (a, bcs) = self.form(pc, test, trial)

        self.P = allocate_matrix(a, bcs=bcs,
                                 form_compiler_parameters=fcp,
                                 mat_type=mat_type,
                                 options_prefix=options_prefix)
        self._assemble_P = create_assembly_callable(a, tensor=self.P,
                                                    bcs=bcs,
                                                    form_compiler_parameters=fcp,
                                                    mat_type=mat_type)
        self._assemble_P()
        self.P.force_evaluation()

        # Transfer nullspace over
        Pmat = self.P.petscmat
        Pmat.setNullSpace(P.getNullSpace())
        tnullsp = P.getTransposeNullSpace()
        if tnullsp.handle != 0:
            Pmat.setTransposeNullSpace(tnullsp)

        # Internally, we just set up a PC object that the user can configure
        # however from the PETSc command line.  Since PC allows the user to specify
        # a KSP, we can do iterative by -assembled_pc_type ksp.
        pc = PETSc.PC().create(comm=opc.comm)
        pc.incrementTabLevel(1, parent=opc)
        pc.setOptionsPrefix(options_prefix)
        pc.setOperators(Pmat, Pmat)
        pc.setFromOptions()
        pc.setUp()
        self.pc = pc

    def update(self, pc):
        self._assemble_P()
        self.P.force_evaluation()

    def form(self, test, trial, pc):
        _, P = pc.getOperators()
        assert P.type == "python"
        context = P.getPythonContext()
        return (context.a, context.row_bcs)

    def apply(self, pc, x, y):
        self.pc.apply(x, y)

    def applyTranspose(self, pc, x, y):
        self.pc.applyTranspose(x, y)

    def view(self, pc, viewer=None):
        super(AssembledPC, self).view(pc, viewer)
        if hasattr(self, "pc"):
            viewer.printfASCII("PC to apply inverse\n")
            self.pc.view(viewer)


class ExplicitSchurPC(AssembledPC):
    """A preconditioner that builds a PC on a specified form.
    Mainly used for describing approximations to Schur complements.
    """

    _prefix = "schur_"

    @abc.abstractmethod
    def form(self, pc, test, trial):
        """

        :arg pc: a `PETSc.PC` object. Use `self.get_appctx(pc)` to get the
             user-supplied application-context, if desired.

        :arg test: a `TestFunction` on this `FunctionSpace`.

        :arg trial: a `TrialFunction` on this `FunctionSpace`.

        This method should return `(a, bcs)`, where `a` is a bilinear `Form`
        and `bcs` is a list of `DirichletBC` boundary conditions (possibly `None`).
        """
        raise NotImplementedError
