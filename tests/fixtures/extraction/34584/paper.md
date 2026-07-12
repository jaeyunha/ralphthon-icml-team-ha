## Foundations of Equivariant Deep Learning: Unifying Graph and Sheaf Neural Networks
<!-- anchor:SEC-0001 -->

## Yoshihiro Maruyama 1
<!-- anchor:SEC-0002 -->

## Abstract
<!-- anchor:SEC-0003 -->

Symmetry is everywhere in nature and society. Geometric deep learning exploits symmetries in data to improve the performance and efficiency of deep learning systems. In this paper, we extend geometric deep learning to utilize richer symmetry structures. Specifically, we develop orderequivariant neural networks (OENN), which generalize standard graph message passing and sheaf neural networks via the theory of equivariant bundles over face posets (face categories). We (i) characterize all linear order-equivariant maps, (ii) build OENN layers, and (iii) prove universal approximation theorems (UATs) for continuous order-equivariant maps, which are new results even when restricted to sheaf neural networks (for which no UAT was known before). We illustrate the framework on graph and sheaf models. Our results can also be seen as extending the known UAT for graph neural networks to a more general setting that subsumes sheaf neural networks as well. In addition, we show that OENN can be extended further to CENN, Category-Equivariant Neural Network, which gives the general form of equivariant neural networks as well as of equivariant universal approximation theorems, allowing us to leverage categorical symmetry in data (e.g., noninvertible symmetries on multiple objects with compositional relations on those symmetries).
<!-- anchor:TXT-0001 -->

## 1. Introduction
<!-- anchor:SEC-0004 -->

Motivation. Symmetry has long been recognized as a powerful inductive bias in deep learning. Group-equivariant architectures explicitly exploit the symmetries of an index set to share parameters, improve sample efficiency, and en-
<!-- anchor:TXT-0002 -->

1 Department of Mathematical and Information Sciences, Kyoto University, Kyoto, Japan. Correspondence to: Yoshihiro Maruyama < maruyama@i.h.kyoto-u.ac.jp > .
<!-- anchor:TXT-0003 -->

Proceedings of the 43 rd International Conference on Machine Learning , Seoul, South Korea. PMLR 306, 2026. Copyright 2026 by the author(s).
<!-- anchor:TXT-0004 -->

sure consistent behavior under transformations of the input domain (Cohen and Welling, 2016; 2017; Weiler and Cesa, 2019; Fuchs et al., 2020; Satorras et al., 2021). Classical convolutional networks are equivariant to translations, while group-equivariant CNNs generalize this idea to arbitrary compact groups. More recently, this principle has been extended to permutation-invariant and permutation-equivariant models such as DeepSets (Zaheer et al., 2017) and graph neural networks GNNs (Gilmer et al., 2017; Xu et al., 2019; Maron et al., 2019), which achieve equivariance with respect to the automorphism group of a graph. However, many data domains are not merely sets or graphs but possess richer hierarchical or incidence structures. Examples include faceposets of graphs, simplicial or CW complexes, and general partially ordered collections of cells or regions. Such domains are naturally indexed by posets, and their symmetries form automorphism groups G = Aut( P, ≤ ) that may involve both permutation and structural (non-invertible or higher-order) relations. This observation motivates the development of order-equivariant neural networks (OENN) that respect the combinatorial structure of a poset rather than a pure group action.
<!-- anchor:TXT-0005 -->

Background and context. The study of equivariance has unified diverse neural architectures under the umbrella of geometric deep learning (Bronstein et al., 2021; Shuman et al., 2013; Bruna et al., 2014; Defferrard et al., 2016). Group- and permutation-equivariant networks (Cohen and Welling, 2016; Zaheer et al., 2017; Gilmer et al., 2017; Xu et al., 2019; Maron et al., 2019) rely on the algebraic structure of groups acting on index sets, while higher-order analogs exploit topological constructions such as simplicial, cellular, or combinatorial complexes (Ebli et al., 2020; Bodnar et al., 2022; Hansen and Gebhart, 2020; Barbero et al., 2022). This includes combinatorial-complex neural networks for topological deep learning (Hajij et al., 2022); in the equivariant line, E ( n ) -equivariant topological neural networks incorporate Euclidean symmetry into topological message passing (Battiloro et al., 2025). Sheaf theory (Curry, 2014) provides a general language for modeling local-to-global dependencies on such structured domains, and recent work on neural sheaf architectures (Hajij et al., 2025; Bamberger et al., 2025; Bodnar et al., 2022; Barbero et al., 2022; Hansen and Gebhart, 2020) shows that combining algebraic-topological tools with deep learning yields strong theoretical and empirical advantages. Our work generalizes these frameworks further: from group- or permutation-equivariant settings to order-equivariant ones, thereby covering both classical GNNs and sheaf-based models as special cases.
<!-- anchor:TXT-0006 -->

## Contributions. We make three contributions:
<!-- anchor:SEC-0005 -->

We give a unified definition of order-equivariant maps between poset-indexed feature bundles and provide a complete orbit-wise characterization of all linear OENN layers via the transporter law and stabilizer intertwiners. This generalizes the block-tying rules of permutation-equivariant networks (Maron et al., 2019) to arbitrary posets.
<!-- anchor:TXT-0007 -->

We turn this linear theory into a nonlinear architecture. OENN layers combine orbital affine maps, equivariant biases, pointwise Reynolds blocks, and pairorbit aggregation, so nonlinearities remain equivariant even when stabilizers act nontrivially on fibers. This yields a hierarchy containing ordinary relationmessage-passing OENNs, source-labeled pair-state OENNs, and full OENNs, and it recovers DeepSets, fixed-graph message passing, vertex-edge incidence updates, and cellular or simplicial sheaf layers as special or further-tied cases (Zaheer et al., 2017; Gilmer et al., 2017; Xu et al., 2019; Curry, 2014; Bodnar et al., 2022; Barbero et al., 2022).
<!-- anchor:TXT-0008 -->

We prove equivariant universal approximation theorems (UATs) for OENNs. The full OENN class is dense in the continuous order-equivariant maps on compact G -invariant sets. We also separate this result from ordinary bounded-depth message passing: standard anonymous aggregation is not universal in general, while pair-state local OENNs compile the global broadcast in directed diameter depth and give a diameter-sharp local universality theorem, with a cover-local corollary for connected Hasse graphs.
<!-- anchor:TXT-0009 -->

Weshow in the appendix that OENN can be extended further to infinitary domains, in particular to CENN, CategoryEquivariant Neural Network, which gives the general form of equivariant neural networks as well as of equivariant universal approximation theorems.
<!-- anchor:TXT-0010 -->

Relation to prior work. Our results can be viewed as a natural extension of the known UATs for permutation- and groupequivariant architectures (Zaheer et al., 2017; Maron et al., 2019; Xu et al., 2019; Cohen and Welling, 2016; Satorras et al., 2021), bringing them under a single formulation that also subsumes sheaf neural networks (Curry, 2014; Hansen and Gebhart, 2020; Barbero et al., 2022; Bodnar et al., 2022). Combinatorial-complex neural networks assign features to cells of a combinatorial complex and update them through incidence, adjacency, or coadjacency relations (Hajij et al., 2022); on a fixed finite complex, such relations are G -stable pair relations on the face poset whenever the automorphism group G ≤ Aut( P, ≤ ) preserves them, so automorphismequivariant CCNN message-passing layers are instances of relation-message-passing OENNs. From a geometric perspective, OENN generalizes the principles of geometric deep learning (Bronstein et al., 2021) to domains indexed by partially ordered sets, bridging discrete symmetry, incidence structure, and topological learning within one unified formalism. The framework of categorical equivariant deep learning develops category-equivariant neural networks in general form, providing both equivariant universality theorems and experimental performance gains (Maruyama, 2025a;b;c; 2026a;b; Maruyama and Yasuda, 2026; Nasu and Maruyama, 2026). OENN may be regarded as a specialization of CENN: the poset supplies the incidence/locality structure and the action groupoid G ⋉ P supplies the categorical naturality condition equivalent to OENN equivariance.
<!-- anchor:TXT-0011 -->

Organization. Section 2 introduces the formal setting of order-equivariant bundles and the construction of OENN layers. Section 3 presents equivariant universal approximation theorems for various types of OENNs. Section 4 illustrates the framework on graphs and sheaves, showing how OENN unifies message-passing and sheaf neural networks. The paper concludes with a brief discussion of significance and applicability. The appendix presents CENN and its relation with OENN as well as all omitted proofs.
<!-- anchor:TXT-0012 -->

## 2. Order-Equivariant Neural Networks
<!-- anchor:SEC-0006 -->

## 2.1. Posets, actions, and equivariant bundles
<!-- anchor:SEC-0007 -->

Let ( P, ≤ ) be a finite poset and let G be a finite group acting on P by order automorphisms; equivalently, fix a homomorphism G → Aut( P, ≤ ) . We write the action as ( γ, p ) ↦→ γp . The full automorphism group case is the special case G = Aut( P, ≤ ) . All vector spaces are finitedimensional real vector spaces.
<!-- anchor:TXT-0013 -->

Definition 2.1 (Equivariant bundle over a poset) . A G -equivariant vector bundle over P consists of vector spaces ( V p ) p ∈ P and linear isomorphisms
<!-- anchor:TXT-0014 -->

$$
T V γ,p : V p → V γp ( γ ∈ G, p ∈ P )
$$
<!-- anchor:EQ-0001 -->

such that T V id ,p = id V p and
<!-- anchor:TXT-0015 -->

$$
T V γη,p = T V γ,ηp ◦ T V η,p ( γ, η ∈ G,p ∈ P ) .
$$
<!-- anchor:EQ-0002 -->

The total feature space is
<!-- anchor:TXT-0016 -->

$$
X := ⊕ p ∈ P V p .
$$
<!-- anchor:EQ-0003 -->

The bundle transports induce a representation ρ X : G → GL( X ) by
<!-- anchor:TXT-0017 -->

$$
( ρ X ( γ ) x ) q = T V γ,γ -1 q x γ -1 q . (1)
$$
<!-- anchor:EQ-0004 -->

Asecond bundle ( W q , T W γ,q ) has total space Y = ⊕ q ∈ P W q and induced action ρ Y by the same formula. A permutationonly bundle is the special case in which all transports are identity maps between canonically identified fibers; then ρ X and ρ Y are block permutations.
<!-- anchor:TXT-0018 -->

Intuition. An element p ∈ P should be read as a site, cell, or component of the structured domain, and the fiber V p is the local feature space carried by that site. A symmetry γ ∈ G relabels sites by p ↦→ γp , while the transport T V γ,p : V p → V γp specifies how feature coordinates are carried along this relabeling. The cocycle identity says that transporting along η and then along γ is the same as transporting along γη , so the direct sum of all fibers inherits a genuine linear G -representation. The order relation on P is not itself a fiber map; rather, it determines natural G -stable relations, masks, and pair-orbits used by the layers below. Sheaf restriction maps are additional structure on such fibers and are incorporated in Section 4.2.
<!-- anchor:TXT-0019 -->

Definition 2.2 (Order-equivariant map) . Let K ⊆ X be G -invariant. A continuous map F : K → Y is orderequivariant if
<!-- anchor:TXT-0020 -->

$$
F ( ρ X ( γ ) x ) = ρ Y ( γ ) F ( x ) ( γ ∈ G, x ∈ K ) . (2)
$$
<!-- anchor:EQ-0005 -->

We write C G ( K,Y ) for the space of continuous orderequivariant maps K → Y . When K = X , we also write C G ( X,Y ) .
<!-- anchor:TXT-0021 -->

## 2.2. Linear and affine order-equivariant maps
<!-- anchor:SEC-0008 -->

Any linear map L : X → Y has a block-kernel representation
<!-- anchor:TXT-0022 -->

$$
( Lx ) q = ∑ p ∈ P K ( q, p ) x p , K ( q, p ) ∈ Hom( V p , W q ) . (3)
$$
<!-- anchor:EQ-0006 -->

> **Theorem/Assumption:** Proposition 2.3 (Transporter law) . A linear map L : X → Y with kernels K ( q, p ) is order-equivariant if and only if
>
> <!-- anchor:THM-0001 -->

$$
K ( γq, γp ) T V γ,p = T W γ,q K ( q, p ) ( γ ∈ G,p, q ∈ P ) . (4)
$$
<!-- anchor:EQ-0007 -->

Let G act diagonally on P × P by γ ( q, p ) = ( γq, γp ) . For a pair-orbit O ∈ ( P × P ) /G , fix a representative ( q O , p O ) and set
<!-- anchor:TXT-0023 -->

$$
H O := { η ∈ G : ηq O = q O , ηp O = p O } .
$$
<!-- anchor:EQ-0008 -->

> **Theorem/Assumption:** Proposition 2.4 (Orbit parametrization) . For each pairorbit O , choose
>
> <!-- anchor:THM-0002 -->

$$
A O ∈ Hom( V p O , W q O )
$$
<!-- anchor:EQ-0009 -->

satisfying
<!-- anchor:TXT-0024 -->

Define
<!-- anchor:TXT-0025 -->

$$
K ( q, p ) := T W γ,q O A O ( T V γ,p O ) -1 (6)
$$
<!-- anchor:EQ-0010 -->

whenever ( q, p ) = γ ( q O , p O ) . Then K is well-defined and satisfies the transporter law. Conversely, every linear orderequivariant map arises uniquely in this way. Hence
<!-- anchor:TXT-0026 -->

$$
dimHom G ( X,Y ) = ∑ O∈ ( P × P ) /G dimHom H O ( V p O , W q O ) .
$$
<!-- anchor:EQ-0011 -->

> **Theorem/Assumption:** Corollary 2.5 (Permutation-only case) . If the input and output bundles are permutation-only, so that source fibers and target fibers in each site-orbit are canonically identified and all transports are identities under these identifications, then the stabilizer constraint is vacuous and, after the same canonical identifications, K ( q, p ) is constant on each pairorbit.
>
> <!-- anchor:THM-0003 -->

Auxiliary finite G -sets. We will also use the same linear theory for auxiliary finite G -sets. If S and T are finite G -sets, X = ⊕ s ∈ S V s and Y = ⊕ t ∈ T W t are equivariant bundles over them, and
<!-- anchor:TXT-0027 -->

$$
( Lx ) t = ∑ s ∈ S K ( t, s ) x s , K ( t, s ) ∈ Hom( V s , W t ) ,
$$
<!-- anchor:EQ-0012 -->

then L is G -equivariant if and only if
<!-- anchor:TXT-0028 -->

$$
K ( γt, γs ) T V γ,s = T W γ,t K ( t, s ) ( γ ∈ G, s ∈ S, t ∈ T ) .
$$
<!-- anchor:EQ-0013 -->

The orbit parametrization is identical with P × P replaced by T × S . Thus an orbital affine layer below may be used between bundles over such auxiliary G -sets, and a mask is equivariant exactly when its support is a union of G -orbits in the relevant target-source product.
<!-- anchor:TXT-0029 -->

Definition 2.6 (Orbital affine layer) . An orbital affine layer is a map A : X → Y of the form A ( x ) = Lx + b , where L is a linear order-equivariant map and b ∈ Y is G -fixed: ρ Y ( γ ) b = b for all γ ∈ G . Equivalently,
<!-- anchor:TXT-0030 -->

$$
b γq = T W γ,q b q .
$$
<!-- anchor:EQ-0014 -->

Thus b is specified by choosing, for each site-orbit representative q 0 , a vector b q 0 ∈ W G q 0 q 0 .
<!-- anchor:TXT-0031 -->

Without biases, the UAT fails for common activations such as ReLU and tanh even for a one-point poset and trivial group, since no-bias networks with σ (0) = 0 vanish at the origin. We include equivariant biases to match the usual affine-map formulation of universal approximation.
<!-- anchor:TXT-0032 -->

$$
T W η,q O A O = A O T V η,p O ( η ∈ H O ) . (5)
$$
<!-- anchor:EQ-0015 -->

## 2.3. Reynolds blocks and OENN layers
<!-- anchor:SEC-0009 -->

An ordinary MLP is a finite composition of affine maps and coordinatewise application of a fixed scalar activation σ : R → R .
<!-- anchor:TXT-0033 -->

Definition 2.7 (Reynolds block) . Let H be a finite group acting linearly on finite-dimensional spaces U and V by representations T U and T V . For an ordinary MLP Ψ : U → V , define
<!-- anchor:TXT-0034 -->

$$
R eq H [Ψ]( u ) := 1 | H | ∑ h ∈ H ( T V h ) -1 Ψ( T U h u ) . (7)
$$
<!-- anchor:EQ-0016 -->

This is called a Reynolds block. If V = R m has the trivial H -action, the corresponding invariant block is
<!-- anchor:TXT-0035 -->

$$
R inv H [Ψ]( u ) := 1 | H | ∑ h ∈ H Ψ(( T U h ) -1 u ) . (8)
$$
<!-- anchor:EQ-0017 -->

> **Theorem/Assumption:** Lemma 2.8 (Equivariance and branch realization) . The map (7) is H -equivariant. Moreover, it is realizable by equivariant affine maps and coordinatewise activations on hidden branch spaces whose H -action is by permutation of branches.
>
> <!-- anchor:THM-0004 -->

Definition 2.9 (Pointwise Reynolds layer) . Let S be a finite G -set, and let E = ⊕ s ∈ S E s and F = ⊕ s ∈ S F s be equivariant bundles over S . For each representative s 0 of a G -orbit in S , choose an ordinary MLP Ψ s 0 : E s 0 → F s 0 and form the Reynolds block
<!-- anchor:TXT-0036 -->

$$
ψ s 0 := R eq G s 0 [Ψ s 0 ] ,
$$
<!-- anchor:EQ-0018 -->

where G s 0 acts on E s 0 and F s 0 by the stabilizer transports. For s = γs 0 , define
<!-- anchor:TXT-0037 -->

$$
ψ s ( e ) := T F γ,s 0 ψ s 0 ( ( T E γ,s 0 ) -1 e ) , e ∈ E s . (9)
$$
<!-- anchor:EQ-0019 -->

The map N : E → F given by ( Nz ) s = ψ s ( z s ) is a pointwise Reynolds layer .
<!-- anchor:TXT-0038 -->

The definition is independent of the choice of γ because ψ s 0 is G s 0 -equivariant. A direct calculation gives Nρ E ( τ ) = ρ F ( τ ) N for every τ ∈ G .
<!-- anchor:TXT-0039 -->

Definition 2.10 (OENN) . An order-equivariant neural network (OENN) on the poset P is any finite composition of orbital affine layers and pointwise Reynolds layers, allowing intermediate equivariant bundles and finite parallel concatenations. Intermediate bundles may be indexed by P or by auxiliary finite G -sets functorially built from P , such as P × P for pair-lift constructions. For auxiliary source and target bundles over finite G -sets S and T , 'orbital affine' means the same transporter-law affine layer with P × P replaced by T × S . Local or masked orbital affine layers are allowed when their supports are unions of pair-orbits in the corresponding target-source product.
<!-- anchor:TXT-0040 -->

When no locality mask is imposed on the orbital affine layers, we call the resulting architecture class the full OENN class. Scalar activations are applied inside ordinary MLP branches, and equivariance for arbitrary stabilizer representations is enforced by Reynolds averaging. In the special case of permutation-only bundles, pointwise Reynolds layers reduce to the usual shared coordinatewise MLP layers.
<!-- anchor:TXT-0041 -->

Definition 2.11 ( R -local layers, pair-state locality, and covers) . Let R ⊆ P × P be a G -invariant relation containing the diagonal. An orbital affine layer A : E → F between bundles indexed by P is called R -local if its kernel blocks satisfy
<!-- anchor:TXT-0042 -->

$$
K ( q, p ) = 0 unless ( q, p ) ∈ R.
$$
<!-- anchor:EQ-0020 -->

Pointwise Reynolds layers are diagonal in the site index and hence are R -local because ∆ P ⊆ R .
<!-- anchor:TXT-0043 -->

The pair-state or source-labeled R -local class, denoted OENN R -pair σ ( X,Y ) , uses hidden bundles whose carrier site q may contain source-indexed slots E q = ⊕ p ∈ P E q,p . The group action sends the p -source slot over q to the γp -source slot over γq . Equivalently, the inter-site hidden state is a bundle over the pair-state set P × P with diagonal G -action. An inter-site orbital affine layer between pair-state bundles is called pair-state R -local if its kernel blocks satisfy the source-preserving support condition
<!-- anchor:TXT-0044 -->

$$
K (( q, p ) , ( r, s )) = 0 unless s = p and ( q, r ) ∈ R.
$$
<!-- anchor:EQ-0021 -->

Thus the carrier coordinate propagates locally along R , while the source label is transported equivariantly and is not mixed during inter-site propagation. The class OENN R -pair σ ( X,Y ) is generated by R -local orbital affine layers on P , pair-state R -local orbital affine layers, pointwise Reynolds layers, carrier-diagonal read/write maps between P -indexed and P × P -indexed bundles, and finite parallel concatenations. Carrier-diagonal maps and pointwise Reynolds layers may act on the whole carrier fiber E q = ⊕ p ∈ P E q,p , but they do not propagate information between different carrier sites. Thus pair-state OENNs preserve the communication pattern of local message passing while retaining the identity of the source site. This is a higher-order local class (rather than the ordinary anonymous-message-passing class).
<!-- anchor:TXT-0045 -->

Write q ≺ p when q < p and no element r ∈ P satisfies q < r < p . The cover-local, order-respecting relation is
<!-- anchor:TXT-0046 -->

$$
R cov := ∆ P ∪ { ( q, p ) : q ≺ p } ∪ { ( q, p ) : p ≺ q } .
$$
<!-- anchor:EQ-0022 -->

Thus an R cov -local layer communicates only along selfloops and one-step up/down Hasse-cover incidences.
<!-- anchor:TXT-0047 -->

## 2.4. Pair-orbit aggregation
<!-- anchor:SEC-0010 -->

We now give a practical aggregation form that is welldefined for arbitrary stabilizer actions. For fixed q ∈ P , put G q := Stab G ( q ) and let
<!-- anchor:TXT-0048 -->

$$
P/G q = { Ω 1 ( q ) , . . . , Ω R ( q ) ( q ) }
$$
<!-- anchor:EQ-0023 -->

be the relative-position classes of source sites as seen from q . Pair-orbits O ∈ ( P × P ) /G meeting { q }× P are canonically in bijection with these classes by
<!-- anchor:TXT-0049 -->

$$
O ↦- → Ω O ( q ) := { p ∈ P : ( q, p ) ∈ O} .
$$
<!-- anchor:EQ-0024 -->

In this sense, pair-orbit aggregation is an order-aggregating block: the summaries S O ( q ; x ) below aggregate over source sites of a fixed relative-position type, while the global pairorbit notation avoids choosing q -dependent representatives.
<!-- anchor:TXT-0050 -->

Let O ∈ ( P × P ) /G be a pair-orbit with representative ( q O , p O ) and stabilizer H O . Choose an H O -invariant Reynolds block φ O : V p O → R m O . For ( q, p ) = γ ( q O , p O ) , define
<!-- anchor:TXT-0051 -->

$$
φ q,p ( v ) := φ O ( ( T V γ,p O ) -1 v ) , v ∈ V p . (10)
$$
<!-- anchor:EQ-0025 -->

This is independent of γ , because changing γ changes it by an element of H O and φ O is H O -invariant. Define the summary
<!-- anchor:TXT-0052 -->

$$
S O ( q ; x ) := ∑ p ∈ P ( q,p ) ∈O φ q,p ( x p ) ∈ R m O , (11)
$$
<!-- anchor:EQ-0026 -->

with the empty sum interpreted as zero.
<!-- anchor:TXT-0053 -->

> **Theorem/Assumption:** Lemma 2.12 (Equivariance of pair summaries) . For all τ ∈ G ,
>
> <!-- anchor:THM-0005 -->

$$
S O ( τq ; ρ X ( τ ) x ) = S O ( q ; x ) .
$$
<!-- anchor:EQ-0027 -->

In particular, S O ( q ; · ) is G q -invariant.
<!-- anchor:TXT-0054 -->

More generally, the same construction can be grouped over any G -invariant relation R ⊆ P × P . Since R is a union of pair-orbits, one may either feed the separate summaries { S O : O ⊂ R } to the readout, or, when the summary dimensions agree and the corresponding encoders are intentionally tied, use the coarsened relation summary
<!-- anchor:TXT-0055 -->

$$
S R ( q ; x ) := ∑ O⊂ R S O ( q ; x ) = ∑ p ∈ P ( q,p ) ∈ R φ R q,p ( x p ) .
$$
<!-- anchor:EQ-0028 -->

Here φ R q,p denotes the tied transported encoder on the pair-orbit containing ( q, p ) . Lemma 2.12 implies S R ( τq ; ρ X ( τ ) x ) = S R ( q ; x ) , so relation-level aggregation is an equivariant parameter-tied coarsening of the orbit-byorbit construction.
<!-- anchor:TXT-0056 -->

For each site-orbit representative q 0 , let A ( q 0 ) be the set of pair-orbits O for which some pair ( q 0 , p ) lies in O . Choose a G q 0 -equivariant Reynolds block
<!-- anchor:TXT-0057 -->

$$
ψ q 0 : V q 0 ⊕ ⊕ O∈A ( q 0 ) R m O → W q 0 ,
$$
<!-- anchor:EQ-0029 -->

where G q 0 acts on V q 0 by the fiber transport and trivially on the summary coordinates. For q = γq 0 , define
<!-- anchor:TXT-0058 -->

$$
F ( x ) q := T W γ,q 0 ψ q 0 ( ( T V γ,q 0 ) -1 x q , { S O ( q ; x ) } O∈A ( q 0 ) ) . (12)
$$
<!-- anchor:EQ-0030 -->

> **Theorem/Assumption:** Proposition 2.13 (Pair-orbit aggregation is an OENN layer) . The map F in (12) is order-equivariant and is realizable as an OENN layer stack.
>
> <!-- anchor:THM-0006 -->

Definition 2.14 (Relation-message-passing OENN layer) . Let R ⊆ P × P be a G -invariant relation containing the diagonal. A relation-message-passing OENN layer is an update obtained from the pair-orbit aggregation construction by using only pair-orbits O ⊆ R :
<!-- anchor:TXT-0059 -->

$$
h ′ q = θ q ( h q , { S O ( q ; h ) } O⊆ R ) . (13)
$$
<!-- anchor:EQ-0031 -->

Here the encoders defining S O are transported invariant Reynolds blocks as in (10)-(11), and the readouts θ q are transported from stabilizer-equivariant Reynolds blocks on site-orbit representatives. If several pair-orbits inside R are intentionally tied and summed before the readout, (13) gives the usual relation-level aggregation. We write OENN R -mp σ for finite compositions of such layers.
<!-- anchor:TXT-0060 -->

> **Theorem/Assumption:** Proposition 2.15 (Message-passing-compatible updates) . Every relation-message-passing OENN layer is an orderequivariant OENN stack. Conversely, any continuous update of the form (13) whose encoders are stabilizer-invariant and whose readouts are stabilizer-equivariant can be uniformly approximated on compact invariant sets by relationmessage-passing OENN layers with any continuous nonpolynomial activation σ .
>
> <!-- anchor:THM-0007 -->

> **Theorem/Assumption:** Proposition 2.16 (Architecture hierarchy) . For every G -invariant relation R ⊆ P × P containing the diagonal and every activation σ used in the OENN layers,
>
> <!-- anchor:THM-0008 -->

$$
OENN R -mp σ ⊆ OENN R -pair σ ⊆ OENN full σ .
$$
<!-- anchor:EQ-0032 -->

The first class is the analog of ordinary local message passing: messages from neighbors in R are aggregated without a persistent global source label. The pair-state class is the universal local completion used in Section 3.3: it keeps the same communication graph but carries a source index through propagation. The full class allows global orbital affine layers.
<!-- anchor:TXT-0061 -->

## 3. Equivariant Universal Approximation
<!-- anchor:SEC-0011 -->

Throughout this section, let ( P, ≤ ) be a finite poset, let G be a finite group acting on P by order automorphisms, and let X = ⊕ p ∈ P V p and Y = ⊕ q ∈ P W q be G -equivariant bundles with actions ρ X and ρ Y . Approximation is measured uniformly on compact G -invariant subsets K ⊂ X .
<!-- anchor:TXT-0062 -->

## 3.1. Preparatory lemmas
<!-- anchor:SEC-0012 -->

> **Theorem/Assumption:** Lemma 3.1 (Sitewise stabilizer equivariance) . Let K ⊆ X be G -invariant. If F ∈ C G ( K,Y ) , then for every q ∈ P and every η ∈ G q := Stab G ( q ) ,
>
> <!-- anchor:THM-0009 -->

$$
F ( ρ X ( η ) x ) q = T W η,q F ( x ) q ( x ∈ K ) .
$$
<!-- anchor:EQ-0033 -->

> **Theorem/Assumption:** Lemma 3.2 (Equivariant density for finite groups) . Let H be a finite group acting linearly on finite-dimensional real vector spaces U and V by T U and T V . Let K ⊂ U be compact and H -invariant, and let f : K → V be continuous and H -equivariant. If σ : R → R is continuous and non-polynomial, then for every norm ‖ · ‖ ∗ on V and every ε > 0 there is an ordinary MLP Ψ : U → V with activation σ such that
>
> <!-- anchor:THM-0010 -->

$$
ψ ( u ) := 1 | H | ∑ h ∈ H ( T V h ) -1 Ψ( T U h u )
$$
<!-- anchor:EQ-0034 -->

is H -equivariant and satisfies
<!-- anchor:TXT-0063 -->

$$
sup u ∈ K ‖ ψ ( u ) -f ( u ) ‖ ∗ < ε.
$$
<!-- anchor:EQ-0035 -->

Moreover, ψ is a Reynolds block and hence is OENNrealizable in the sense of Lemma 2.8.
<!-- anchor:TXT-0064 -->

## 3.2. Full universal approximation
<!-- anchor:SEC-0013 -->

Wefirst consider OENN full σ ( X,Y ) , i.e., the class of OENNs from Definition 2.10 in which arbitrary orbital affine layers are allowed.
<!-- anchor:TXT-0065 -->

> **Theorem/Assumption:** Theorem 3.3 (Full OENN UAT) . Let ( P, ≤ ) be finite and let G be a finite group acting on P by order automorphisms. Let X = ⊕ p ∈ P V p and Y = ⊕ q ∈ P W q be G -equivariant bundles. Let K ⊂ X be compact and G -invariant, and let σ : R → R be continuous and non-polynomial. Then OENN full σ ( X,Y ) is dense in C G ( K,Y ) in the uniform norm. Equivalently, for every f ∈ C G ( K,Y ) and every ε > 0 , there exists a full OENN F : X → Y such that
>
> <!-- anchor:THM-0011 -->

$$
sup x ∈ K ‖ F ( x ) -f ( x ) ‖ < ε.
$$
<!-- anchor:EQ-0036 -->

Note that local masks such as cover, incidence, or one-hop graph relations are equivariant whenever they are G -stable, but bounded-depth local equivariance alone does not imply universal approximation.
<!-- anchor:TXT-0066 -->

> **Theorem/Assumption:** Corollary 3.4 (Permutation-only UAT) . Assume that the original input and output transports are identity maps between canonically identified fibers, so that G acts by block permutations. Then the linear part of OENN specializes to affine layers whose blocks and biases are tied on G -orbits. Ordinary sitewise pointwise layers reduce to shared MLPs on site-orbits, while stabilizer-equivariant readouts on auxiliary broadcast fibers are finite Reynolds averages over permutation representations. Consequently, Theorem 3.3 specializes to universal approximation of continuous G -equivariant maps on compact invariant subsets for finite permutation-group actions. In full-symmetric invariantoutput special cases, this is compatible with DeepSetstype sum-of-embeddings representations, while for graphindexed features it gives the full fixed-domain orbit-tied equivariant approximation class.
>
> <!-- anchor:THM-0012 -->

## 3.3. Pair-state local message-passing universality
<!-- anchor:SEC-0014 -->

The proof of Theorem 3.3 uses a global broadcast layer. We now show that the same effect can be obtained by local message passing, provided the hidden state is allowed to be pair-state : the state z q,p is stored at carrier site q and remembers that it originated at source site p . This is the local analog of higher-order or tensorized GNNs; it keeps the same communication graph as ordinary anonymous aggregation.
<!-- anchor:TXT-0067 -->

For a G -invariant relation R ⊆ P × P containing the diagonal, let Γ R be the directed communication graph with vertex set P and edge p → q exactly when ( q, p ) ∈ R . Thus R records which source sites p may send information to which target sites q in one carrier-local linear layer. Write d R ( p, q ) for the directed distance from p to q , with d R ( p, q ) = ∞ if no such path exists.
<!-- anchor:TXT-0068 -->

> **Theorem/Assumption:** Theorem 3.5 (Diameter-sharp pair-state local universality) . Let R ⊆ P × P be a G -invariant relation containing the diagonal, and let Γ R and d R be as above.
>
> <!-- anchor:THM-0013 -->

(i) Lower bound. Fix L ≥ 0 . Consider any architecture whose input feature at site p is initially available only at p , whose inter-site layers have support contained in R , and whose remaining operations are pointwise nonlinearities, carrier-diagonal equivariant maps, or finite parallel concatenations. Then the output at q after at most L inter-site layers depends only on input sites p with d R ( p, q ) ≤ L . Consequently, if d R ( p, q ) > L , then even for trivial G , scalar fibers, and compact domain [0 , 1] P , no such L -local architecture can uniformly approximate the continuous map whose q -coordinate is f ( x ) q = x p and whose other coordinates are zero.
<!-- anchor:TXT-0069 -->

(ii) Diameter-depth compilation. If Γ R is strongly connected with directed diameter D , then the broadcast layer
<!-- anchor:TXT-0070 -->

$$
B : X → ⊕ q ∈ P ˜ X q , ˜ X q := X, ( Bx ) q = x,
$$
<!-- anchor:EQ-0037 -->

with transport T ˜ X γ,q = ρ X ( γ ) is exactly realizable by pairstate R -local OENN primitives using D inter-site propagation layers. The construction uses hidden pair-state variables z q,p ∈ V p ( q, p ∈ P ) , so the hidden width at each carrier site scales as ∑ p ∈ P dim V p .
<!-- anchor:TXT-0071 -->

(iii) Universality. Under the same strong-connectivity hy- pothesis, for every continuous non-polynomial activation σ : R → R , OENN R -pair σ ( X,Y ) is dense in C G ( K,Y ) in the uniform norm. Moreover, the depth threshold is sharp in the worst-case sense that, for every L < D , the lower-bound statement applies to some pair of sites p, q with d R ( p, q ) > L .
<!-- anchor:TXT-0072 -->

> **Theorem/Assumption:** Corollary 3.6 (Pair-state cover-local OENN UAT) . Let R cov be the cover-local relation from Definition 2.11. If the undirected Hasse graph of P is connected, then OENN R cov -pair σ ( X,Y ) is dense in C G ( K,Y ) in the uniform norm.
>
> <!-- anchor:THM-0014 -->

There are several remarks. The cover-local relation R cov contains both upward and downward cover incidences. This is necessary for universal approximation of arbitrary equivariant maps X → Y , because an arbitrary output site may depend on features at any other site. If communication is restricted to only one order direction, the directed communication graph of a nontrivial finite poset is generally not strongly connected. In that case one can obtain universality only for maps satisfying the corresponding causal orderdependence restriction.
<!-- anchor:TXT-0073 -->

> **Theorem/Assumption:** Theorem 3.5 is a universality theorem for the pair-state local completion. Ordinary message passing aggregates neighbor information without a persistent source label; pair-state propagation stores z q,p and therefore lets the readout at q access the contribution from each source p separately. Some mechanism of this kind (source labels, higher-order states, global attention, or a global broadcast) is unavoidable for worst-case approximation of arbitrary maps in C G ( K,Y ) .
>
> <!-- anchor:THM-0015 -->

The hypothesis on σ is the usual finite-dimensional MLP hypothesis. ReLU and tanh satisfy it. Coordinatewise activations need not commute with arbitrary nontrivial fiber transports; this is why OENN uses Reynolds blocks for stabilizer representations.
<!-- anchor:TXT-0074 -->

## 4. Examples: Graphs and Sheaves
<!-- anchor:SEC-0015 -->

## 4.1. Fixed graphs via face-posets
<!-- anchor:SEC-0016 -->

Let G = ( V, E ) be a finite undirected graph without parallel edges, and let P := V ⊔ E be its face-poset, with v ≤ e iff v is an endpoint of e . Every graph automorphism preserves incidence and hence acts on P by poset automorphisms.
<!-- anchor:TXT-0075 -->

Vertex-only layers. Take permutation-only vertex fibers V v ≃ R d in and W v ≃ R d out . For a fixed graph, Proposition 2.4 gives the most general linear Aut( G ) -equivariant vertex operator:
<!-- anchor:TXT-0076 -->

$$
( Lh ) v = ∑ O∈ ( V × V ) / Aut( G ) A O ∑ u ∈ V ( v,u ) ∈O h u . (14)
$$
<!-- anchor:EQ-0038 -->

For a general graph, the pair-orbits need not be only 'self' and 'adjacent'. If Aut( G ) is trivial, every ordered pair is its own orbit. The standard message-passing linear layer
<!-- anchor:TXT-0077 -->

$$
( Lh ) v = A self h v + A adj ∑ u ∈ N ( v ) h u (15)
$$
<!-- anchor:EQ-0039 -->

is nevertheless equivariant, because the diagonal relation ∆ = { ( v, v ) : v ∈ V } and the directed adjacency relation E ± = { ( v, u ) : { v, u } ∈ E } are unions of pair-orbits. Thus (15) is an OENN layer with additional parameter tying across all self-pair orbits and all adjacency-pair orbits. It coincides with the full orbit-parametrized form only in the special case where the target-source pair-orbits in V × V are exactly the diagonal relation and the directed adjacency relation. More generally, within the adjacency-supported masked subspace, it is full only when both ∆ and E ± are single pair-orbits; otherwise it additionally ties distinct orbit blocks and sets all non-adjacency orbit kernels to zero.
<!-- anchor:TXT-0078 -->

The usual nonlinear message-passing update
<!-- anchor:TXT-0079 -->

$$
h ′ v = ψ   h v , ∑ u ∈ N ( v ) φ ( h u )   (16)
$$
<!-- anchor:EQ-0040 -->

is obtained from the invariant-relation aggregation above with R = ∆ ∪ E ± : the explicit self input h v is the diagonal term, while one ties the encoders for all pair-orbits contained in E ± and sums their summaries before the readout. Hence ordinary MPNNs are OENN special cases, while the full OENN class can express finer orbit-dependent sharing on a fixed graph.
<!-- anchor:TXT-0080 -->

Local universality and MPNNs. For fixed graphs, the local UAT in Theorem 3.5 is concerned with the pair-state local completion. In graph notation, the universal local hidden state is z v,u : it is carried by vertex v but remembers the source vertex u . Local propagation updates
<!-- anchor:TXT-0081 -->

$$
z t +1 v,u = ∑ w ∈ N [ v ] z t w,u ,
$$
<!-- anchor:EQ-0041 -->

where N [ v ] includes the self-loop, followed by an equivariant rescaling after diameter-many steps. This is a secondorder/source-aware message-passing architecture on V × V . The ordinary MPNN (16) is recovered by discarding the persistent source label and tying messages by the adjacency relation; that tied anonymous subclass is not universal for arbitrary continuous equivariant maps on a fixed graph.
<!-- anchor:TXT-0082 -->

Cycles. Let G = C n be the cycle with vertex set Z n . Under the cyclic subgroup C n , pair-orbits are directed offsets
<!-- anchor:TXT-0083 -->

$$
O ℓ = { ( i, i + ℓ ) : i ∈ Z n } , ℓ ∈ Z n .
$$
<!-- anchor:EQ-0042 -->

Thus a C n -equivariant linear layer is ordinary circular convolution:
<!-- anchor:TXT-0084 -->

$$
( Lh ) i = ∑ ℓ ∈ Z n A ℓ h i + ℓ . (17)
$$
<!-- anchor:EQ-0043 -->

Under the full dihedral group D 2 n , reflection identifies offsets ℓ and -ℓ . The pair-orbits are indexed by undirected distance k ∈ { 0 , 1 , . . . , ⌊ n/ 2 ⌋} , and the equivariant filters are
<!-- anchor:TXT-0085 -->

$$
( Lh ) i = A 0 h i + ∑ 1 ≤ k<n/ 2 A k ( h i + k + h i -k ) + 1 2 | n A n/ 2 h i + n/ 2 . (18)
$$
<!-- anchor:EQ-0044 -->

Therefore, for n ≥ 3 and nonzero input and output fiber dimensions, the dihedral distance-isotropic filters are a strict subset of cyclic circular convolutions, obtained from (17) by imposing A ℓ = A -ℓ for every offset ℓ .
<!-- anchor:TXT-0086 -->

Vertex-edge couplings. If edge fibers are included, then Proposition 2.4 also describes vertex-edge and edge-vertex blocks. Let h v ∈ R d V be vertex features, z e ∈ R d E edge features, and let the vertex output fiber be R d ′ V . A common incidence-tied vertex update is
<!-- anchor:TXT-0087 -->

$$
( Lx ) v = A V V, 0 h v + A V V, 1 ∑ u ∈ N ( v ) h u + A V E, inc ∑ e ∋ v z e , (19)
$$
<!-- anchor:EQ-0045 -->

with A V V, 0 , A V V, 1 ∈ Hom( R d V , R d ′ V ) and A V E, inc ∈ Hom( R d E , R d ′ V ) . Edge outputs can analogously use selfedge, incident-vertex, and edge-adjacency masks. Relations such as { ( v, e ) : v ≤ e } are unions of pair-orbits and therefore define equivariant orbital affine layers. On an arbitrary fixed graph, however, (19) is generally a coarser tied special case of the full orbit-parametrized operator: in highly symmetric graphs the incidence mask may collapse to a small number of orbit types, while in asymmetric graphs it may split into many pair-orbits.
<!-- anchor:TXT-0088 -->

## 4.2. Cellular and simplicial sheaf layers
<!-- anchor:SEC-0017 -->

Let K be a finite regular CW complex or simplicial complex with face-poset P , and let G be a finite group acting on P by order automorphisms. A cellular sheaf assigns a vector space V p to each cell p ∈ P and a restriction map
<!-- anchor:TXT-0089 -->

$$
R p → q : V p → V q ( q ≤ p ) ,
$$
<!-- anchor:EQ-0046 -->

compatible along chains. We use this contravariant faceposet convention throughout: q ≤ p means that q is a face of p , and restrictions point from the larger cell to the face. Reversing the poset recovers the opposite convention used in some neural-sheaf formulations. Suppose this G -action lifts to the sheaf, meaning
<!-- anchor:TXT-0090 -->

$$
T V γ,q R p → q = R γp → γq T V γ,p ( q ≤ p ) . (20)
$$
<!-- anchor:EQ-0047 -->

> **Theorem/Assumption:** Lemma 4.1 (Invariant fiber metrics and sheaf adjoints) . For every finite lifted action satisfying (20) , there exist inner products on all fibers V p for which every transport T V γ,p : V p → V γp is an isometry. With respect to any such invariant inner products, the adjoints of the restriction maps satisfy
>
> <!-- anchor:THM-0016 -->

$$
T V γ,p R ∗ p → q = R ∗ γp → γq T V γ,q ( q ≤ p, γ ∈ G ) . (21)
$$
<!-- anchor:EQ-0048 -->

Linear sheaf-type orbital layers. Let W = ⊕ q ∈ P W q be a G -equivariant output bundle. Consider the strict upward relation
<!-- anchor:TXT-0091 -->

$$
U ◦ := { ( q, p ) : q < p }
$$
<!-- anchor:EQ-0049 -->

and the strict downward relation
<!-- anchor:TXT-0092 -->

$$
D ◦ := { ( q, r ) : r < q } .
$$
<!-- anchor:EQ-0050 -->

Both are unions of pair-orbits, and diagonal self terms are treated separately. For an upward pair-orbit O ⊂ U ◦ with representative ( q O , p O ) , choose
<!-- anchor:TXT-0093 -->

$$
B ↑ O ∈ Hom( V q O , W q O )
$$
<!-- anchor:EQ-0051 -->

and set
<!-- anchor:TXT-0094 -->

$$
A ↑ O := B ↑ O R p O → q O ∈ Hom( V p O , W q O ) .
$$
<!-- anchor:EQ-0052 -->

We require A ↑ O to satisfy the stabilizer condition (5). Then Proposition 2.4 transports A ↑ O to all pairs in O , giving an equivariant upward sheaf block. A simple sufficient way to ensure this condition is to choose B ↑ O as an intertwiner for the target fiber representation,
<!-- anchor:TXT-0095 -->

$$
T W η,q O B ↑ O = B ↑ O T V η,q O ( η ∈ H O ) .
$$
<!-- anchor:EQ-0053 -->

Indeed, since η fi xes both q O and p O , naturality gives T V η,q O R p O → q O = R p O → q O T V η,p O , and hence T W η,q O A ↑ O = A ↑ O T V η,p O . This sufficient condition is not necessary; the most general requirement is still the stabilizer condition on the composed block A ↑ O .
<!-- anchor:TXT-0096 -->

For downward terms, use the G -invariant inner products from Lemma 4.1, so that adjoints are compatible with transports by (21). If r ≤ q , then
<!-- anchor:TXT-0097 -->

$$
R ∗ q → r : V r → V q .
$$
<!-- anchor:EQ-0054 -->

For a downward pair-orbit O ⊂ D ◦ with representative ( q O , r O ) , choose
<!-- anchor:TXT-0098 -->

$$
B ↓ O ∈ Hom( V q O , W q O ) , A ↓ O := B ↓ O R ∗ q O → r O ∈ Hom( V r O , W q O ) ,
$$
<!-- anchor:EQ-0055 -->

again satisfying the stabilizer condition. Self terms are handled by blocks A 0 O ∈ Hom( V q O , W q O ) on pair-orbits contained in the diagonal. Analogously, the stronger but constructive condition
<!-- anchor:TXT-0099 -->

$$
T W η,q O B ↓ O = B ↓ O T V η,q O ( η ∈ H O )
$$
<!-- anchor:EQ-0056 -->

implies the required stabilizer condition for A ↓ O , because (21) gives T V η,q O R ∗ q O → r O = R ∗ q O → r O T V η,r O .
<!-- anchor:TXT-0100 -->

The resulting linear layer has the form
<!-- anchor:TXT-0101 -->

$$
x ′ q = K 0 ( q, q ) x q + ∑ p : q<p K ↑ ( q, p ) x p + ∑ r : r<q K ↓ ( q, r ) x r , (22)
$$
<!-- anchor:EQ-0057 -->

where the kernels are transported from the orbit representatives as in (6). The following lemma gives the explicit transporter-law verification.
<!-- anchor:TXT-0102 -->

> **Theorem/Assumption:** Lemma 4.2 (Sheaf orbital transporter law) . The self, upward, and downward kernels in (22) , transported from the orbit representatives as in (6) and satisfying the stabilizer conditions above, satisfy the transporter law (4) . Hence (22) is order-equivariant.
>
> <!-- anchor:THM-0017 -->

Special shared-fiber case. In the permutation-only case, or more generally when the fibers are globally identified and the shared blocks B 0 , B ↑ , B ↓ are chosen to intertwine all relevant transports and stabilizer actions, the orbit-wise notation reduces to the familiar shared formula
<!-- anchor:TXT-0103 -->

$$
x ′ q = B 0 x q + ∑ p : q<p B ↑ R p → q x p + ∑ r : r<q B ↓ R ∗ q → r x r , (23)
$$
<!-- anchor:EQ-0058 -->

where B ↑ and B ↓ act after the restriction or adjoint has landed in the fiber at q . This is a special case of the orbitwise transported layer in (22).
<!-- anchor:TXT-0104 -->

Nonlinear sheaf aggregation. A nonlinear sheaf layer is obtained by applying the pair-orbit aggregation construction to the strict comparable-pair orbits in U ◦ and D ◦ , together with a pointwise self term on the diagonal. On an upward orbit, form the pair feature R p → q x p ∈ V q in the auxiliary pair bundle with fiber V q over ( q, p ) ; naturality (20) gives the required transporter law. On a downward orbit, form R ∗ q → r x r ∈ V q ; the adjoint naturality (21) gives the corresponding transporter law. The encoders are chosen invariant under the corresponding pair stabilizers, and the final cellwise readout is a pointwise Reynolds layer. This gives an equivariant nonlinear sheaf-type OENN layer and correctly handles orientation signs or other nontrivial stabilizer actions without double-counting diagonal contributions.
<!-- anchor:TXT-0105 -->

UATin the sheaf-indexed setting. By Theorem 3.3, the full OENN class on the face-poset of a fixed complex is dense in the continuous maps between total sheaf-valued feature spaces that are equivariant for the chosen lifted finite group action, uniformly on compact invariant sets. If the undirected Hasse graph of the face-poset is connected, Corollary 3.6 compiles the broadcast used in the proof into finitely many cover-local up/down propagation layers on pair-states ( q, p ) , where q is the carrier cell and p is the source cell. Consequently, pair-state cover-local sheaf-indexed OENNs are also universal, provided depth is allowed to scale at least with the Hasse-graph diameter and source-cell-labeled memory is allowed. Note that, without such source-aware global mixing, local sheaf diffusion or sheaf message-passing lay- ers such as (23) remain equivariant but are not universal in general.
<!-- anchor:TXT-0106 -->

## 5. Conclusion
<!-- anchor:SEC-0018 -->

We have developed order-equivariant neural networks (OENNs) as a unified framework for learning on structured domains whose coordinates are organized not only by a set or a graph, but by an ordered incidence geometry. We have shown that equivariant deep learning can be formulated in terms of equivariant bundles over posets: symmetries move sites, transports move local feature coordinates, and neural layers are precisely constrained by the resulting compatibility laws. This viewpoint simultaneously recovers familiar graph message passing, higher-order vertex-edge interactions, and cellular or simplicial sheaf layers, while also identifying the strictly more expressive orbit-wise and pairstate constructions that are invisible in ordinary anonymous aggregation.
<!-- anchor:TXT-0107 -->

Beyond the unification of architectures, we have shown that full OENNs give universal approximation for continuous order-equivariant maps on compact invariant domains, while the local theory separates genuine locality from mere parameter tying: bounded-depth local message passing is not universally expressive in general, but source-aware pairstate propagation restores universality once information can traverse the Hasse graph. Thus the framework supplies a principled methodology for choosing architectures: use coarse relation-message passing when the task only requires tied local aggregation, and use orbit-wise, sheaf-aware, or pair-state mechanisms when the task depends on incidence type, orientation, stabilizer actions, or long-range structured interactions.
<!-- anchor:TXT-0108 -->

The broader applicability of OENN is not limited to the examples treated explicitly here. Many scientific and geometric data sets are naturally indexed by cells, regions, events, sensors, strata, or multiscale components equipped with incidence or restriction relations. In such settings, the present theory suggests a systematic route from domain structure to architecture: specify the ordered or categorical index space, lift the relevant symmetries to feature fibers, and derive equivariant layers from transporter and stabilizer constraints rather than by ad hoc sharing rules. The appendix places OENN inside the more general category-equivariant neural network (CENN) framework, where posets are replaced by categories and action groupoids; this extension connects the present theory to broader category-equivariant models and applications (Maruyama, 2025a;b;c; 2026a;b; Maruyama and Yasuda, 2026), which demonstrate how the extended equivariant models help to improve the experimental performance of classic equivariant models in concrete machine learning tasks. In such a way, geometric deep learning can be extended from groups to categories.
<!-- anchor:TXT-0109 -->

## Impact Statement
<!-- anchor:SEC-0019 -->

This paper aims to advance symmetry-aware machine learning research. There seem to be no societal consequences of this theoretical research on geometric deep learning that would need to be specifically highlighted here.
<!-- anchor:TXT-0110 -->

## References
<!-- anchor:SEC-0020 -->

Bamberger, J., Barbero, F., Dong, X., and Bronstein, M. M. Bundle Neural Network for message diffusion on graphs. In The Thirteenth International Conference on Learning Representations , 2025.
<!-- anchor:TXT-0111 -->

Barbero, F., Bodnar, C., S´ aez de Oc´ ariz Borde, H., Bronstein, M., Veliˇ ckovi´ c, P., and Li` o, P. Sheaf Neural Networks with Connection Laplacians. In Proceedings of Topological, Algebraic, and Geometric Learning Workshops 2022 , volume 196 of Proceedings of Machine Learning Research , pages 28-36. PMLR, 2022.
<!-- anchor:TXT-0112 -->

Battiloro, C., Karaismailo˘ glu, E., Tec, M., Dasoulas, G., Audirac, M., and Dominici, F. E ( n ) -equivariant topological neural networks. In The Thirteenth International Conference on Learning Representations , 2025.
<!-- anchor:TXT-0113 -->

Bodnar, C., Di Giovanni, F., Chamberlain, B. P., Li` o, P., and Bronstein, M. M. Neural sheaf diffusion: A topological perspective on heterophily and oversmoothing in GNNs. In Advances in Neural Information Processing Systems , volume 35, pages 18527-18541, 2022.
<!-- anchor:TXT-0114 -->

Bronstein, M. M., Bruna, J., Cohen, T., and Veliˇ ckovi´ c, P. Geometric deep learning: Grids, groups, graphs, geodesics, and gauges. arXiv:2104.13478, 2021.
<!-- anchor:TXT-0115 -->

Bruna, J., Zaremba, W., Szlam, A., and LeCun, Y. Spectral networks and locally connected networks on graphs. In International Conference on Learning Representations , 2014.
<!-- anchor:TXT-0116 -->

Cohen, T. S. and Welling, M. Group equivariant convolutional networks. In Proceedings of the 33rd International Conference on Machine Learning , volume 48 of Proceedings of Machine Learning Research , pages 2990-2999. PMLR, 2016.
<!-- anchor:TXT-0117 -->

Cohen, T. S. and Welling, M. Steerable CNNs. In International Conference on Learning Representations , 2017.
<!-- anchor:TXT-0118 -->

Curry, J. Sheaves, Cosheaves and Applications . PhD thesis, University of Pennsylvania, 2014.
<!-- anchor:TXT-0119 -->

Defferrard, M., Bresson, X., and Vandergheynst, P. Convolutional neural networks on graphs with fast localized spectral filtering. In Advances in Neural Information Processing Systems , volume 29, pages 3844-3852, 2016.
<!-- anchor:TXT-0120 -->

Ebli, S., Defferrard, M., and Spreemann, G. Simplicial neural networks. In NeurIPS 2020 Workshop on Topological Data Analysis and Beyond , 2020.
<!-- anchor:TXT-0121 -->

Fuchs, F. B., Worrall, D. E., Fischer, V., and Welling, M. SE(3)-transformers: 3D roto-translation equivariant attention networks. In Advances in Neural Information Processing Systems , volume 33, pages 1970-1981, 2020.
<!-- anchor:TXT-0122 -->

Gilmer, J., Schoenholz, S. S., Riley, P. F., Vinyals, O., and Dahl, G. E. Neural message passing for quantum chemistry. In Proceedings of the 34th International Conference on Machine Learning , volume 70 of Proceedings of Machine Learning Research , pages 1263-1272. PMLR, 2017.
<!-- anchor:TXT-0123 -->

Hajij, M., Bastian, L., Osentoski, S., Kabaria, H., Davenport, J. L., Dawood, S., Cherukuri, B., Kocheemoolayil, J. G., Shahmansouri, N., Lew, A., Papamarkou, T., and Birdal, T. Copresheaf topological neural networks: A generalized deep learning framework. In Advances in Neural Information Processing Systems , volume 38, pages 149759-149803, 2025.
<!-- anchor:TXT-0124 -->

Hajij, M., Zamzmi, G., Papamarkou, T., Miolane, N., Guzm´ an-S´ aenz, A., Ramamurthy, K. N., Birdal, T., Dey, T. K., Mukherjee, S., Samaga, S. N., Livesay, N., Walters, R., Rosen, P., and Schaub, M. T. Topological deep learning: Going beyond graph data. arXiv:2206.00606, 2022.
<!-- anchor:TXT-0125 -->

Hansen, J. and Gebhart, T. Sheaf neural networks. In NeurIPS 2020 Workshop on Topological Data Analysis and Beyond , 2020.
<!-- anchor:TXT-0126 -->

Khan, A. M., Khawaja, S. G., Akram, M. U., and Khan, A. S. sEMG dataset of routine activities. Data in Brief , 33:106543, 2020.
<!-- anchor:TXT-0127 -->

Khan, A. M., Khawaja, S. G., Akram, M. U., and Khan, A. S. Physical Action Dataset. Mendeley Data, V2, 2020. doi:10.17632/bcv9vsxkyc.2.
<!-- anchor:TXT-0128 -->

Leshno, M., Lin, V. Y., Pinkus, A., and Schocken, S. Multilayer feedforward networks with a nonpolynomial activation function can approximate any function. Neural Networks , 6(6):861-867, 1993.
<!-- anchor:TXT-0129 -->

Maron, H., Ben-Hamu, H., Shamir, N., and Lipman, Y. Invariant and equivariant graph networks. In International Conference on Learning Representations , 2019.
<!-- anchor:TXT-0130 -->

Maruyama, Y. Categorical equivariant deep learning: Category-equivariant neural networks and universal approximation theorems. arXiv:2511.18417, 2025.
<!-- anchor:TXT-0131 -->

Maruyama, Y. Learning with category-equivariant representations for human activity recognition. arXiv:2511.00900, 2025.
<!-- anchor:TXT-0132 -->

Maruyama, Y. Learning with category-equivariant architectures for human activity recognition. arXiv:2511.01139, 2025.
<!-- anchor:TXT-0133 -->

Maruyama, Y. Category-equivariant regularization for fewshot multirate time-series learning. In Proceedings of the International Joint Conference on Neural Networks , 2026.
<!-- anchor:TXT-0134 -->

Maruyama, Y. Infinity-Categorical Deep Learning for Human Activity Recognition. Accepted for publication in Lecture Notes in Computer Science . Springer, 2026.
<!-- anchor:TXT-0135 -->

Maruyama, Y. and Yasuda, A. Grothendieck categoryequivariant neural networks for human activity recognition. In Lecture Notes in Computer Science . Springer, 2026.
<!-- anchor:TXT-0136 -->

Nasu, R. and Maruyama, Y. Mathematical foundations of monoid-equivariant neural networks. In Proceedings of the 28th International Conference on Pattern Recognition , 2026.
<!-- anchor:TXT-0137 -->

Satorras, V. G., Hoogeboom, E., and Welling, M. E(n) equivariant graph neural networks. In Proceedings of the 38th International Conference on Machine Learning , volume 139 of Proceedings of Machine Learning Research , pages 9323-9332. PMLR, 2021.
<!-- anchor:TXT-0138 -->

Shuman, D. I., Narang, S. K., Frossard, P., Ortega, A., and Vandergheynst, P. The emerging field of signal processing on graphs: Extending high-dimensional data analysis to networks and other irregular domains. IEEE Signal Processing Magazine , 30(3):83-98, 2013.
<!-- anchor:TXT-0139 -->

Weiler, M. and Cesa, G. General E(2)-equivariant steerable CNNs. In Advances in Neural Information Processing Systems , volume 32, pages 14334-14345, 2019.
<!-- anchor:TXT-0140 -->

Xu, K., Hu, W., Leskovec, J., and Jegelka, S. How powerful are graph neural networks? In International Conference on Learning Representations , 2019.
<!-- anchor:TXT-0141 -->

Zaheer, M., Kottur, S., Ravanbakhsh, S., P´ oczos, B., Salakhutdinov, R. R., and Smola, A. J. Deep Sets. In Advances in Neural Information Processing Systems , volume 30, pages 3391-3401, 2017.
<!-- anchor:TXT-0142 -->

## A. Category-Equivariant Neural Networks and Their Relation with OENNs
<!-- anchor:SEC-0021 -->

This appendix presents the framework of categoryequivariant neural networks (CENNs) and explains how the OENN framework is obtained from it; some experimental results are provided as well (Maruyama, 2025a;b;c; 2026a;b; Maruyama and Yasuda, 2026). CENN is concerned with categorical equivariance with respect to transformations beyond invertible symmetries (i.e., non-invertible symmetries on/between multiple objects). Non-invertible categorical symmetry is extensively studied in the recent development of mathematical and theoretical physics. CENN explores the same idea of non-invertible categorical symmetry in the context of geometric deep learning.
<!-- anchor:TXT-0143 -->

In a group-equivariant network, one fixes representations ρ X , ρ Y of a group G and requires F ( ρ X ( g ) x ) = ρ Y ( g ) F ( x ) . Equivalently, the network commutes with all invertible changes of viewpoint encoded by the one-object category obtained from G . CENN replaces this one-object group by a possibly multi-object category C . Its objects can represent typed feature sites, cells, regions, sensor states, local contexts, or levels of resolution, while its arrows can represent admissible transports, restrictions, incidence relations, causal updates, coarse-to-fine maps, or local symmetries. Thus the arrows of C describe not only which symmetries should be respected, but also which transformations are allowed to move information between different feature types. The naturality condition gives the categorical generalization of equivariance.
<!-- anchor:TXT-0144 -->

Formally, input and output feature spaces are organized as contravariant functors to the category Meas of measurable spaces and measurable maps X,Y : C op -→ Meas or as functors to topological vector spaces equipped with their Borel structures. A category-equivariant layer is then a family of maps F a : X ( a ) → Y ( a ) satisfying the naturality equation Y ( u ) ◦ F a = F b ◦ X ( u ) where u : b → a . This is the categorical extension of equivariance. Note that u need not be invertible and the two ends of u need not have the same type. Consequently, the same equation can express ordinary group equivariance, compatibility with order restrictions, invariance under irreversible time updates, sheaf-like local-to-global consistency, and orbitwise consistency for local symmetries.
<!-- anchor:TXT-0145 -->

This viewpoint gives a unified language for the noninvertible and multi-object transformations listed in Table 1 (Maruyama, 2025a). Since arrows in a category compose, categorical equivariance is not merely a list of separate parameter-sharing constraints. The constraints must be compatible with categorical composition. For example, if two restrictions or transports can be composed in the data domain, then the corresponding neural maps must compose coherently as well. This functorial compatibility is what distinguishes categorical equivariance from an ad hoc collection of tied weights, masks, or pooling rules.
<!-- anchor:TXT-0146 -->

Beyond single types of categorical symmetry such as groups, graphs, sheaves and logics (lattices), CENN can accommodate compositional symmetries , such as Group × Poset (product category), and contextual symmetries , such as ∫ c ∈C F ( c ) (Grothendieck construction), which integrates local symme- tries F ( c ) over the base context category C . For instance, a signal may carry both a global group symmetry and a hierarchical incidence structure represented by a poset; categorically, this can be modeled by the product category of the group and the poset (where both are seen as categories). Moreover, local symmetry types may vary over a base context category C . Let F ( c ) denote the local category of transformations available at context c . Then, the Grothendieck construction
<!-- anchor:TXT-0147 -->

**Table:** [table on page 12]

Assets: assets/TAB-0001.json, assets/TAB-0001.csv
<!-- anchor:TAB-0001 -->

**Table:** Table 1. Categorical equivariance across domains.

Assets: assets/TAB-0002.json, assets/TAB-0002.csv
<!-- anchor:TAB-0002 -->

$$
∫ c ∈C F ( c )
$$
<!-- anchor:EQ-0059 -->

assembles these varying local symmetries into one category. This can be regarded as the categorical extension of semidirect product of groups: instead of one group acting uniformly everywhere, the available transformations can depend on object type, context, or stratum, while still composing coherently.
<!-- anchor:TXT-0148 -->

In the following subsections of the appendix, we give a more formal account of CENN and analyze the relation between CENN and OENN. We show, in particular, that completed OENN input-output maps are embedded into CENN through the action groupoid of the chosen symmetry action, while hidden pair-state and branch constructions may use auxiliary action groupoids built from the same action. Note that they are not embedded through the thin poset category alone. The poset order supplies incidence, masks, covers, and sheaf-type restriction structure; the equivariance in OENN is supplied by the group acting by order automorphisms.
<!-- anchor:TXT-0149 -->

## A.1. CENN basics
<!-- anchor:SEC-0022 -->

We first explain the basics of the CENN formalism. A category serves as an indexing device for the transformations under which a network must be equivariant. Objects are feature sites or feature types, and arrows are admissible changes of viewpoint, restrictions, transports, or symmetries.
<!-- anchor:TXT-0150 -->

Categorical index spaces. Formally, a small category C consists of a set of objects Ob( C ) , arrow sets Hom C ( b, a ) , identity arrows id a : a → a , and an associative composition law. We write
<!-- anchor:TXT-0151 -->

$$
s ( u ) = b, t ( u ) = a
$$
<!-- anchor:EQ-0060 -->

for the source and target of an arrow u : b → a . If v : c → b and u : b → a , then u ◦ v : c → a .
<!-- anchor:TXT-0152 -->

Three basic examples are useful.
<!-- anchor:TXT-0153 -->

A group G is a one-object category BG with Hom( ∗ , ∗ ) = G ; naturality over BG is ordinary group equivariance.
<!-- anchor:TXT-0154 -->

A poset ( P, ≤ ) is a thin category with one arrow p → q iff p ≤ q ; naturality over it is compatibility with orderrestriction maps.
<!-- anchor:TXT-0155 -->

If G acts on a set S , the action groupoid G ⋉ S has objects s ∈ S and arrows s → γs labeled by γ ∈ G ; naturality over it is equivariance under the action of G .
<!-- anchor:TXT-0156 -->

To introduce categorical convolutional layers, we also need topology and measures on arrows. A measured topological category is a small category such that each hom-set Hom C ( b, a ) is a second-countable locally compact Hausdorff space, composition is continuous, and each hom-set carries a σ -finite Radon measure µ b,a . We additionally impose the local countability/Radon condition needed by the category-convolution formula we use below: for each target object a , the set of sources b with nonzero incoming measure is countable, and the incoming-arrow space
<!-- anchor:TXT-0157 -->

$$
I ( a ) := ⊔ b ∈ Ob( C ) Hom C ( b, a ) , µ a := ⊕ b µ b,a (24)
$$
<!-- anchor:EQ-0061 -->

with the disjoint-union topology is itself second-countable locally compact Hausdorff and carries the σ -finite Radon measure µ a . Equivalently, one may take the measurable topological spaces ( I ( a ) , µ a ) as part of the CENN data, with the displayed hom-set restrictions. Thus I ( a ) is the space of all arrows through which the a -component of a layer can read information. In finite specializations, including the OENN specialization below, the topology is discrete, µ b,a is counting measure, and integrals over I ( a ) are finite sums.
<!-- anchor:TXT-0158 -->

Feature functors. Let Meas denote the category of measurable spaces and measurable maps. A CENN feature space is a contravariant functor
<!-- anchor:TXT-0159 -->

$$
Z : C op -→ Meas .
$$
<!-- anchor:EQ-0062 -->

Thus each object a carries a measurable space Z ( a ) , and each arrow u : b → a induces a measurable pullback/transport
<!-- anchor:TXT-0160 -->

$$
Z ( u ) : Z ( a ) -→ Z ( b ) ,
$$
<!-- anchor:EQ-0063 -->

satisfying
<!-- anchor:TXT-0161 -->

$$
Z (id a ) = id Z ( a ) , Z ( u ◦ v ) = Z ( v ) ◦ Z ( u )
$$
<!-- anchor:EQ-0064 -->

for v : c → b and u : b → a . In the analytic layers below, each Z ( a ) is the Borel measurable space underlying a topological vector space and each structural transport Z ( u ) is continuous linear. The contravariant convention means that an arrow into a lets a field on a be restricted or transported to the arrow source.
<!-- anchor:TXT-0162 -->

The analytic CENN model realizes these measurable spaces as Borel spaces underlying topological vector spaces of continuous local fields. For every object a , choose a compact base space Ω( a ) and a finite-dimensional real fiber E Z ( a ) , and set
<!-- anchor:TXT-0163 -->

$$
Z ( a ) := C (Ω( a ) , E Z ( a )) . (25)
$$
<!-- anchor:EQ-0065 -->

We equip this field space with the compact-open topology, equivalently the sup-norm topology in the present compact finite-dimensional setting, and with its Borel σ -algebra. For each arrow u : b → a , choose continuous base maps
<!-- anchor:TXT-0164 -->

$$
π u : Ω( b ) → Ω( a ) , τ u : Ω( a ) → Ω( b ) ,
$$
<!-- anchor:EQ-0066 -->

and a linear fiber transport
<!-- anchor:TXT-0165 -->

$$
L Z u : E Z ( a ) → E Z ( b ) .
$$
<!-- anchor:EQ-0067 -->

Here π u defines the pullback of fields, while τ u is the sampling map used by the convolutional kernel. Functoriality requires, for v : c → b and u : b → a ,
<!-- anchor:TXT-0166 -->

$$
π u ◦ v = π u ◦ π v , τ u ◦ v = τ v ◦ τ u , L Z u ◦ v = L Z v ◦ L Z u ,
$$
<!-- anchor:EQ-0068 -->

with identity maps on identity arrows. The induced action on local fields is
<!-- anchor:TXT-0167 -->

$$
Z ( u ) h := L Z u ◦ h ◦ π u ∈ C (Ω( b ) , E Z ( b )) , h ∈ Z ( a ) . (26)
$$
<!-- anchor:EQ-0069 -->

When every base is a point, Ω( a ) = {∗} , this reduces to the finite-dimensional point-base case
<!-- anchor:TXT-0168 -->

$$
Z ( a ) ∼ = E Z ( a ) , Z ( u ) = L Z u : E Z ( a ) → E Z ( b ) .
$$
<!-- anchor:EQ-0070 -->

This is the case used to embed OENN below, with finitedimensional vector spaces understood as Borel measurable spaces.
<!-- anchor:TXT-0169 -->

Equivariance as naturality. Let X,Y : C op → Meas be feature functors whose object spaces also carry the topologies used for approximation.
<!-- anchor:TXT-0170 -->

Definition A.1 (Category-equivariant maps) . A continuous category-equivariant map from X to Y is a natural transformation in Meas
<!-- anchor:TXT-0171 -->

$$
Φ : X ⇒ Y, Φ = { Φ a : X ( a ) → Y ( a ) } a ∈ Ob( C ) ,
$$
<!-- anchor:EQ-0071 -->

whose components are continuous maps. Equivalently, every Φ a is measurable and continuous, and for every arrow u : b → a , the square
<!-- anchor:TXT-0172 -->

$$
X ( a ) Φ a - - → Y ( a ) X ( u ) ↓ ↓ Y ( u ) X ( b ) Φ b - - → Y ( b )
$$
<!-- anchor:EQ-0072 -->

commutes. Written as an equation,
<!-- anchor:TXT-0173 -->

$$
Y ( u ) ◦ Φ a = Φ b ◦ X ( u ) . (27)
$$
<!-- anchor:EQ-0073 -->

No linearity of the components Φ a is assumed. We write EqvCont( X,Y ) for the space of such natural transformations in Meas with continuous components.
<!-- anchor:TXT-0174 -->

The approximation topology on EqvCont( X,Y ) is the compact-open finite-object topology. In the normed localfield setting used for the UAT, a basic seminorm is specified by a finite set F ⊂ Ob( C ) and compact sets K a ⊂ X ( a ) :
<!-- anchor:TXT-0175 -->

$$
‖ Φ ‖ F, ( K a ) := max a ∈ F sup x ∈ K a ‖ Φ a ( x ) ‖ ∞ . (28)
$$
<!-- anchor:EQ-0074 -->

Approximation therefore means uniform approximation on finitely many objects and compact subsets of their feature spaces.
<!-- anchor:TXT-0176 -->

This definition contains the usual equivariance notions. If C = BG has one object and arrows a group G , then a contravariant functor is a representation up to the inverse convention, and (27) is the usual equation
<!-- anchor:TXT-0177 -->

$$
F ( ρ X ( g ) x ) = ρ Y ( g ) F ( x ) .
$$
<!-- anchor:EQ-0075 -->

If C is a thin poset category, naturality is compatibility with order arrows. If C is an incidence or face category, naturality is sheaf-like compatibility with incidence restrictions.
<!-- anchor:TXT-0178 -->

Categorical convolution. The basic affine CENN layer is a convolution over incoming arrows. Let Z, Z ′ : C op → Meas be field-type feature functors represented by local vector fields as above, with continuous linear structural transports. A category kernel assigns, for every incoming arrow u : b → a and point y ∈ Ω( a ) , a linear map
<!-- anchor:TXT-0179 -->

$$
K ( u, y ) : E Z ( b ) → E Z ′ ( a ) .
$$
<!-- anchor:EQ-0076 -->

Assume the standard regularity needed for the integral below: measurability in u , continuity in y , and an L 1 bound over I ( a ) on compact parameter ranges. A bias is a family β a ∈ Z ′ ( a ) satisfying
<!-- anchor:TXT-0180 -->

$$
Z ′ ( u ) β a = β b ( u : b → a ) .
$$
<!-- anchor:EQ-0077 -->

For z ∈ Z ( a ) , define
<!-- anchor:TXT-0181 -->

$$
( ( ˜ L K ) a z ) ( y ) := β a ( y ) + ∫ I ( a ) K ( u, y ) ( Z ( u ) z ) ( τ u y ) dµ a ( u ) . (29)
$$
<!-- anchor:EQ-0078 -->

Here u : b → a , so Z ( u ) z ∈ Z ( b ) and ( Z ( u ) z )( τ u y ) ∈ E Z ( b ) , exactly the domain of K ( u, y ) .
<!-- anchor:TXT-0182 -->

The kernel is called natural when the affine family is a continuous natural transformation Z ⇒ Z ′ in Meas . Equivalently, for every arrow w : a → c ,
<!-- anchor:TXT-0183 -->

$$
Z ′ ( w )( ˜ L K ) c = ( ˜ L K ) a Z ( w ) . (30)
$$
<!-- anchor:EQ-0079 -->

Written pointwise for z ∈ Z ( c ) and y ∈ Ω( a ) , the non-bias terms satisfy
<!-- anchor:TXT-0184 -->

$$
L Z ′ w ∫ I ( c ) K ( u ′ , π w y ) ( Z ( u ′ ) z ) ( τ u ′ π w y ) dµ c ( u ′ ) = ∫ I ( a ) K ( u, y ) ( Z ( w ◦ u ) z ) ( τ u y ) dµ a ( u ) .
$$
<!-- anchor:EQ-0080 -->

For finite point-base categories, (29) becomes the finite sum
<!-- anchor:TXT-0185 -->

$$
( ˜ L K ) a z = β a + ∑ u : b → a K ( u ) Z ( u ) z. (31)
$$
<!-- anchor:EQ-0081 -->

Thus CENN convolution is the categorical analog of a tiedweight equivariant affine layer.
<!-- anchor:TXT-0186 -->

Natural nonlinearities. Nonlinearities must also commute with the category action. Let S : C op → Meas be the scalar feature functor
<!-- anchor:TXT-0187 -->

$$
S ( a ) = C (Ω( a ) , R ) , S ( u ) r = r ◦ π u ,
$$
<!-- anchor:EQ-0082 -->

equipped with the compact-open Borel measurable structure. A scalar channel is a natural transformation s : Z ⇒ S in Meas whose components are continuous. Given a scalar activation α : R → R , the associated scalar-gated nonlinearity is
<!-- anchor:TXT-0188 -->

$$
( Σ α,s a z ) ( y ) = α ( s a ( z )( y ) ) z ( y ) . (32)
$$
<!-- anchor:EQ-0083 -->

Naturality of s implies naturality of Σ α,s . With the trivial scalar functor S above, the usual coordinatewise activation is recovered from scalar gates only when the relevant coordinate projection is itself a natural scalar channel. In the finite point-base case this means that the coordinate is fixed by every stabilizer element acting on its fiber. For a finite-dimensional trivial scalar coordinate, adding a constant channel gives
<!-- anchor:TXT-0189 -->

$$
r ↦-→ (1 , r j ) ↦-→ α ( r j )(1 , r j ) ,
$$
<!-- anchor:EQ-0084 -->

whose first component is α ( r j ) .
<!-- anchor:TXT-0190 -->

On a nontrivial permutation representation, an individual coordinate projection is generally not natural as a map to the trivial scalar functor: if a stabilizer element sends coordinate j to coordinate k , naturality would force r j = r k for all vectors r . Thus scalar gates into S do not by themselves implement unrestricted coordinatewise activations on permutation branches. Coordinatewise activations on equivariant collections of scalar slots must instead be typed as natural maps for the corresponding permutation-scalar functor, or else be placed inside the branch MLP and equivariantized by the Reynolds construction used for OENN. For arbitrary nontrivial stabilizer representations, raw coordinate projections are generally not natural, and coordinatewise activations need not commute with transport; this is why the OENN construction uses natural scalar channels or Reynolds-equivariant pointwise blocks rather than unrestricted coordinatewise nonlinearities.
<!-- anchor:TXT-0191 -->

Definition A.2 (CENN) . Fix a continuous non-polynomial scalar activation α ; in the general CENN UAT, it is also assumed globally Lipschitz. A category-equivariant neural network from X to Y is a finite composition of continuous natural layers in Meas generated by category-convolutions, scalar-gated nonlinearities, finite direct sums/parallel channels, and arrow-bundle lift/convolution/compilation layers (Maruyama, 2025a). The resulting class is denoted
<!-- anchor:TXT-0192 -->

$$
CENN α ( X,Y ) .
$$
<!-- anchor:EQ-0085 -->

The detailed definitions of these arrow-bundle generators are in (Maruyama, 2025a). In the finite action-groupoid specialization used below, only their structural consequences are needed: finite direct sums of transported arrow samples, finite CENN convolutions on those arrow-indexed bundles, and finite equivariant averages that compile the arrow-bundle features back to the target functor.
<!-- anchor:TXT-0193 -->

Because natural transformations in Meas with continuous components are closed under composition and finite vectorspace direct sums equipped with their Borel σ -algebras,
<!-- anchor:TXT-0194 -->

$$
CENN α ( X,Y ) ⊆ EqvCont( X,Y ) .
$$
<!-- anchor:EQ-0086 -->

Equivariant universal approximation. The CENN UAT of (Maruyama, 2025a) says that, under mild analytic hypotheses on the category, the converse inclusion holds after closure. The hypotheses have the following operational meaning.
<!-- anchor:TXT-0195 -->

Approximate identities: kernels on I ( a ) can localize near a chosen incoming arrow. In finite categories these are Dirac masses δ u .
<!-- anchor:TXT-0196 -->

Arrow-probe separation: the transported samples appearing in (29) separate points on the compact sets being approximated. In finite point-base categories, identity arrows recover the original features, so separation is automatic.
<!-- anchor:TXT-0197 -->

Equivariant compilation: approximants constructed on arrow-bundle features can be reassembled into a natural transformation with values in the target functor. In finite groupoids, this is finite averaging over the relevant arrows or stabilizers.
<!-- anchor:TXT-0198 -->

> **Theorem/Assumption:** Theorem A.3 (CENN UAT) . Assume the standard CENN hypotheses above, with X and Y fi eld-type Meas -valued functors whose object spaces carry the topologies and norms used in the compact-open seminorms. Let α : R → R be continuous, non-polynomial, and globally Lipschitz. Then
>
> <!-- anchor:THM-0018 -->

$$
CENN α ( X,Y ) = EqvCont( X,Y )
$$
<!-- anchor:EQ-0087 -->

in the compact-open finite-object topology. Equivalently, for every Φ ∈ EqvCont( X,Y ) , every finite F ⊂ Ob( C ) , every compact K a ⊂ X ( a ) for a ∈ F , and every ε > 0 , there exists Ψ ∈ CENN α ( X,Y ) such that
<!-- anchor:TXT-0199 -->

$$
max a ∈ F sup x ∈ K a ‖ Φ a ( x ) -Ψ a ( x ) ‖ ∞ < ε.
$$
<!-- anchor:EQ-0088 -->

For the reader mainly interested in OENN, the finite specialization is the essential case: C is a finite discrete action groupoid, all bases are points, all integrals are sums, approximate identities are point masses, arrow probes separate because identity arrows are present, and equivariant compilation is finite groupoid averaging. The next subsection makes this specialization explicit.
<!-- anchor:TXT-0200 -->

## A.2. Relationship with OENNs
<!-- anchor:SEC-0023 -->

We now identify completed OENN maps over P as finite action-groupoid, point-base specializations of CENN; auxiliary OENN states are represented over the action groupoids of their corresponding finite G -sets. Let ( P, ≤ ) be a finite poset, let G be a finite group acting on P by order automorphisms, and let
<!-- anchor:TXT-0201 -->

$$
X tot = ⊕ p ∈ P V p , Y tot = ⊕ q ∈ P W q
$$
<!-- anchor:EQ-0089 -->

be OENN input and output bundles with transports T V γ,p and T W γ,q as in Definition 2.1.
<!-- anchor:TXT-0202 -->

Define the action groupoid
<!-- anchor:TXT-0203 -->

$$
A := G ⋉ P.
$$
<!-- anchor:EQ-0090 -->

Its objects are elements of P , and an arrow
<!-- anchor:TXT-0204 -->

$$
( γ, p ) : p -→ γp
$$
<!-- anchor:EQ-0091 -->

is specified by γ ∈ G and p ∈ P . Composition is
<!-- anchor:TXT-0205 -->

$$
( η, γp ) ◦ ( γ, p ) = ( ηγ, p ) .
$$
<!-- anchor:EQ-0092 -->

This is a finite discrete category, equipped with counting measure. The ordinary OENN bundle V is equivalently the point-base CENN feature functor
<!-- anchor:TXT-0206 -->

$$
V : A op → Meas , V ( p ) = V p , V ( γ, p ) = ( T V γ,p ) -1 : V γp → V p .
$$
<!-- anchor:EQ-0093 -->

Here each finite-dimensional vector space carries its Borel measurable structure, and the transport maps are measurable linear isomorphisms. Contravariant functoriality is exactly the cocycle identity for the transports. The same construction gives a functor W from the output bundle. This objectwise bundle functor is useful, but it is not yet the correct encoding of an arbitrary OENN map X tot → Y tot , because an OENN output at a site q may depend on all input sites, not only on V q .
<!-- anchor:TXT-0207 -->

For maps between total feature spaces, define instead the global-input functor
<!-- anchor:TXT-0208 -->

$$
op
$$
<!-- anchor:EQ-0094 -->

$$
X : A → Meas , X ( q ) := X tot , X ( γ, q ) := ρ X ( γ -1 ) : X tot → X tot ,
$$
<!-- anchor:EQ-0095 -->

and the site-output functor
<!-- anchor:TXT-0209 -->

$$
Y : A op → Meas , Y ( q ) := W q , Y ( γ, q ) := ( T W γ,q ) -1 : W γq → W q .
$$
<!-- anchor:EQ-0096 -->

Here ( γ, q ) : q → γq is an arrow of A . Point bases are understood, so X ( q ) and Y ( q ) are finite-dimensional vector spaces equipped with their Borel measurable structures, rather than spaces of nontrivial fields; their structural maps are continuous linear maps.
<!-- anchor:TXT-0210 -->

These global-input/site-output functors classify a completed map from a full source state to sitewise outputs. They are not meant to type an arbitrary OENN stack as a single composable chain of CENN natural transformations: after such a completed map, the codomain object at q is W q , whereas the next OENN layer would again read a full hidden total state. For the layerwise formulation, let H = ⊕ s ∈ S H s be an intermediate equivariant bundle over a finite G -set S , with total action ρ H , and let H ′ = ⊕ t ∈ T H ′ t be the next target bundle over a finite G -set T . On the target action groupoid G ⋉ T , use the total-source functor
<!-- anchor:TXT-0211 -->

$$
H ( t ) := H tot , H ( γ, t ) := ρ H ( γ -1 ) : H tot → H tot ,
$$
<!-- anchor:EQ-0097 -->

together with the site-output functor
<!-- anchor:TXT-0212 -->

$$
H ′ ( t ) := H ′ t , H ′ ( γ, t ) := ( T H ′ γ,t ) -1 : H ′ γt → H ′ t .
$$
<!-- anchor:EQ-0098 -->

Thus an OENN layer H tot → H ′ tot is represented by a natural family H ⇒ H ′ , and layers are composed after assembling these families into maps between total feature spaces.
<!-- anchor:TXT-0213 -->

For a compact G -invariant set K ⊂ X tot , let
<!-- anchor:TXT-0214 -->

$$
Nat K ( X , Y )
$$
<!-- anchor:EQ-0099 -->

denote families of continuous maps Φ q : K → W q satisfying the naturality equation on K .
<!-- anchor:TXT-0215 -->

> **Theorem/Assumption:** Proposition A.4 (OENN equivariance as CENN naturality) . The assignment
>
> <!-- anchor:THM-0019 -->

$$
F ↦-→ Φ F , Φ F q ( x ) := F ( x ) q ,
$$
<!-- anchor:EQ-0100 -->

defines a canonical linear bijection
<!-- anchor:TXT-0216 -->

$$
C G ( K,Y tot ) ∼ = Nat K ( X , Y ) .
$$
<!-- anchor:EQ-0101 -->

Under this bijection, the uniform norm on C G ( K,Y tot ) induced by the product max norm on Y tot is exactly the compact-open finite-object seminorm with F = P and K q = K for all q ∈ P .
<!-- anchor:TXT-0217 -->

Proof. Naturality for the arrow ( γ, q ) : q → γq says
<!-- anchor:TXT-0218 -->

$$
Y ( γ, q )Φ γq ( x ) = Φ q ( X ( γ, q ) x ) , x ∈ K.
$$
<!-- anchor:EQ-0102 -->

By the definitions of X and Y , this is
<!-- anchor:TXT-0219 -->

$$
( T W γ,q ) -1 Φ γq ( x ) = Φ q ( ρ X ( γ -1 ) x ) . (33)
$$
<!-- anchor:EQ-0103 -->

Since K is G -invariant, replacing x by ρ X ( γ ) x gives the equivalent equation
<!-- anchor:TXT-0220 -->

$$
Φ γq ( ρ X ( γ ) x ) = T W γ,q Φ q ( x ) . (34)
$$
<!-- anchor:EQ-0104 -->

If F ( x ) q := Φ q ( x ) , then (34) is precisely the γq -coordinate of
<!-- anchor:TXT-0221 -->

$$
F ( ρ X ( γ ) x ) = ρ Y ( γ ) F ( x ) .
$$
<!-- anchor:EQ-0105 -->

Thus natural families are exactly continuous orderequivariant maps. Finally,
<!-- anchor:TXT-0222 -->

$$
max q ∈ P sup x ∈ K ‖ Φ q ( x ) -Ψ q ( x ) ‖ = sup x ∈ K ‖ F Φ ( x ) -F Ψ ( x ) ‖ Y tot , max ,
$$
<!-- anchor:EQ-0106 -->

which proves the topological assertion.
<!-- anchor:TXT-0223 -->

> **Theorem/Assumption:** Proposition A.5 (OENN primitives as finite CENN primitives) . With the primitivewise typing convention above, each completed OENN primitive, viewed through its site-output family after assembly, is represented by finite point-base CENN primitives over action groupoids of the finite G -sets indexing that primitive and its auxiliary branch states. Thus the primitive-level comparison uses action groupoids G ⋉ S for auxiliary finite G -sets S that occur in the OENN stack, rather than forcing every hidden primitive to live literally over the single object set P .
>
> <!-- anchor:THM-0020 -->

An OENN orbital affine layer is an identity-supported category-convolution from the relevant total-source functor to the site-output target functor.
<!-- anchor:TXT-0224 -->

A pointwise Reynolds layer over any finite G -set S is a finite CENN stack over G ⋉ S , together with the finite branch auxiliary action groupoids used to realize its Reynolds block.
<!-- anchor:TXT-0225 -->

Pair-state OENN layers are the same construction over the auxiliary action groupoid G ⋉ ( P × P ) , with additional G -stable support restrictions encoding locality.
<!-- anchor:TXT-0226 -->

Proof. Let S and T be finite G -sets, and let
<!-- anchor:TXT-0227 -->

$$
H tot = ⊕ s ∈ S H s , H ′ tot = ⊕ t ∈ T H ′ t
$$
<!-- anchor:EQ-0107 -->

be equivariant bundles. An orbital affine layer between them has the form
<!-- anchor:TXT-0228 -->

$$
A ( h ) t = b t + ∑ s ∈ S K ( t, s ) h s .
$$
<!-- anchor:EQ-0108 -->

Write
<!-- anchor:TXT-0229 -->

$$
L t : H tot → H ′ t , L t ( h ) := ∑ s ∈ S K ( t, s ) h s .
$$
<!-- anchor:EQ-0109 -->

The naturality equation for the corresponding completed affine family H ⇒ H ′ over G ⋉ T is
<!-- anchor:TXT-0230 -->

$$
( T H ′ γ,t ) -1 L γt = L t ρ H ( γ -1 ) , ( T H ′ γ,t ) -1 b γt = b t .
$$
<!-- anchor:EQ-0110 -->

Equivalently,
<!-- anchor:TXT-0231 -->

$$
L γt ρ H ( γ ) = T H ′ γ,t L t , b γt = T H ′ γ,t b t .
$$
<!-- anchor:EQ-0111 -->

Expanding the first identity in the H s -source blocks gives exactly the transporter law
<!-- anchor:TXT-0232 -->

$$
K ( γt, γs ) T H γ,s = T H ′ γ,t K ( t, s ) ,
$$
<!-- anchor:EQ-0112 -->

and the second identity is the OENN fixed-bias law. With counting measure and point bases, define a category kernel supported only at the identity arrow of each target object by
<!-- anchor:TXT-0233 -->

̸
<!-- anchor:TXT-0234 -->

$$
K (id t ) := L t , K ( u ) := 0 ( u = id t in I ( t )) .
$$
<!-- anchor:EQ-0113 -->

Then the CENN convolution formula gives ( ˜ L K h ) t = b t + L t h , and its naturality condition is exactly the equation above. Hence orbital affine layers, including those between auxiliary finite G -sets, are identity-supported CENN category-convolutions.
<!-- anchor:TXT-0235 -->

For a pointwise Reynolds layer over a finite G -set S , the stabilizer average
<!-- anchor:TXT-0236 -->

$$
ψ s 0 ( u ) = 1 | G s 0 | ∑ h ∈ G s 0 ( T F h,s 0 ) -1 Ψ s 0 ( T E h,s 0 u )
$$
<!-- anchor:EQ-0114 -->

is a finite groupoid average. Its branch realization is typed with finite auxiliary branch action groupoids whose objects are the branch labels h ∈ G s 0 appearing in Lemma 2.8, transported along the orbit of s 0 ; the stabilizer permutes these labels, while each branch object carries ordinary finitedimensional trivial scalar coordinates. The affine maps in the branch realization are affine natural maps between these branch functors, and the scalar activation is applied by scalar gates only to the trivial scalar coordinates of each branch object, as in (32). If the same branch labels are folded into a single fiber ( R n ) G s 0 , the coordinatewise activation remains equivariant for the permutation action, but it should be regarded as the corresponding natural permutation-feature nonlinearity, or as part of the Reynolds pointwise primitive, not as a scalar gate into the trivial scalar functor S . Transporting the representative block along the orbit by
<!-- anchor:TXT-0237 -->

$$
ψ γs 0 ( e ) = T F γ,s 0 ψ s 0 ( ( T E γ,s 0 ) -1 e )
$$
<!-- anchor:EQ-0115 -->

is precisely the naturality condition in G ⋉ S . Thus pointwise Reynolds layers are finite CENN stacks.
<!-- anchor:TXT-0238 -->

Finally, pair-state layers replace S by P × P with diagonal action γ ( q, p ) = ( γq, γp ) . A locality mask such as
<!-- anchor:TXT-0239 -->

$$
K (( q, p ) , ( r, s )) = 0 unless s = p and ( q, r ) ∈ R
$$
<!-- anchor:EQ-0116 -->

is not a new equivariance law; it is a G -stable support restriction on an otherwise ordinary finite action-groupoid CENN kernel.
<!-- anchor:TXT-0240 -->

> **Theorem/Assumption:** Lemma A.6 (Finite CENN UAT layers are OENN-realizable) . Let A = G ⋉ P be the finite action groupoid above, with point bases and finite-dimensional Borel feature spaces. The finite CENN approximants needed in the CENN UAT proof over A can be chosen to be realizable by full OENN primitives after allowing the auxiliary finite G -sets already permitted in Definition 2.10. Consequently, if Ψ is one of these chosen finite action-groupoid CENN approximants from Theorem A.3, then the assembled map
>
> <!-- anchor:THM-0021 -->

$$
F Ψ : X tot → Y tot , F Ψ ( x ) q := Ψ q ( x ) ,
$$
<!-- anchor:EQ-0117 -->

belongs to OENN full α ( X tot , Y tot ) .
<!-- anchor:TXT-0241 -->

Proof. A point-base CENN hidden functor Z : A op → Meas in the finite construction has finite-dimensional vector spaces Z ( q ) with invertible linear transports. For an arrow ( γ, q ) : q → γq , write
<!-- anchor:TXT-0242 -->

$$
T Z γ,q := Z ( γ, q ) -1 : Z ( q ) → Z ( γq ) .
$$
<!-- anchor:EQ-0118 -->

Functoriality of Z is exactly the cocycle identity for the transports T Z , so the family { Z ( q ) , T Z γ,q } is an equivariant bundle over the finite G -set P . The same observation applies to any finite direct sum or arrow-bundle hidden functor: its slots are indexed by a finite G -set built functorially from arrows of A or finite tuples of such arrows, and the structural maps are the corresponding bundle transports.
<!-- anchor:TXT-0243 -->

Consider first an affine CENN layer in the layerwise totalsource form Λ : H ⇒ H ′ over G ⋉ T , where H tot = ⊕ s ∈ S H s . Write
<!-- anchor:TXT-0244 -->

$$
Λ t ( h ) = c t + ∑ s ∈ S Λ t,s h s , Λ t,s : H s → H ′ t .
$$
<!-- anchor:EQ-0119 -->

Naturality for the arrow ( γ, t ) : t → γt says
<!-- anchor:TXT-0245 -->

$$
( T H ′ γ,t ) -1 Λ γt ( h ) = Λ t ( ρ H ( γ -1 ) h ) .
$$
<!-- anchor:EQ-0120 -->

Equivalently, after replacing h by ρ H ( γ ) h and comparing the H s -blocks,
<!-- anchor:TXT-0246 -->

$$
Λ γt,γs T H γ,s = T H ′ γ,t Λ t,s , c γt = T H ′ γ,t c t .
$$
<!-- anchor:EQ-0121 -->

Thus a global-input affine CENN layer is exactly an orbital affine OENN layer between the associated equivariant bundles over the finite G -sets S and T .
<!-- anchor:TXT-0247 -->

If an affine hidden layer is presented objectwise as Z ⇒ Z ′ over a single action groupoid G ⋉ S , write Λ s ( z ) = c s + λ s z . Naturality gives
<!-- anchor:TXT-0248 -->

$$
λ γs T Z γ,s = T Z ′ γ,s λ s , c γs = T Z ′ γ,s c s ,
$$
<!-- anchor:EQ-0122 -->

which is the same transporter law with diagonal source support. In a multilayer stack, each assembled codomain total space is then retyped as the next total-source functor, as described above. Finite category-convolutions are affine natural layers of this form, since the integral in (29) is a finite sum in the relevant finite action groupoid. The arrowbundle lift, probe, and compilation maps used in the CENN UAT proof (Maruyama, 2025a) are built from finite direct sums of transports, coordinate inclusions/projections, and finite groupoid averages; hence they are affine natural maps and therefore orbital affine OENN layers by the preceding argument.
<!-- anchor:TXT-0249 -->

It remains only to check nonlinearities. We use the finite UAT construction in branch-MLP form: scalar gates are used only for coordinates that are trivial natural scalar channels, as described after (32). Branch spaces carrying a nontrivial permutation action are not treated as if their individual coordinate projections were natural for the trivial scalar functor. When the same scalar activation is applied coordinatewise to such an equivariant array, it is used as a vector-valued equivariant branch operation, not as a scalar gate into S ; in the OENN realization used here, it is placed inside the ordinary branch MLP and then equivariantized by the Reynolds construction of Lemma 2.8. For nontrivial stabilizer actions, the resulting equivariant pointwise operation is therefore represented by a pointwise Reynolds layer. We do not assert that an arbitrary scalar gate in an arbitrary CENN architecture is exactly an OENN primitive; the claim is only that the finite approximants required for the action-groupoid UAT can be chosen inside the full OENN primitive class. Since full OENNs are closed under finite composition and finite parallel concatenation, each chosen finite CENN approximant in the finite action-groupoid case assembles to a full OENN.
<!-- anchor:TXT-0250 -->

> **Theorem/Assumption:** Corollary A.7 (CENN UAT and OENN UAT) . For the action groupoid A = G ⋉ P and the global-input/site- output functors X , Y above, write
>
> <!-- anchor:THM-0022 -->

$$
CENN α ( X , Y ) | K
$$
<!-- anchor:EQ-0123 -->

for the restrictions to K of CENN natural transformations. Then the compact-domain form of the CENN UAT gives
<!-- anchor:TXT-0251 -->

$$
CENN α ( X , Y ) | K = Nat K ( X , Y ) ∼ = C G ( K,Y tot )
$$
<!-- anchor:EQ-0124 -->

for every compact G -invariant K ⊂ X tot , whenever the activation satisfies the general CENN UAT hypotheses. By Lemma A.6, the finite action-groupoid CENN approximants may be chosen to assemble to full OENNs, so the same density statement gives the categorical form of the full OENN UAT
<!-- anchor:TXT-0252 -->

$$
OENN full α ( X tot , Y tot ) | K = C G ( K,Y tot ) .
$$
<!-- anchor:EQ-0125 -->

For globally Lipschitz continuous non-polynomial α , this follows from the general CENN theorem and the finiterealization lemma above. The OENN theorem in Section 3 is slightly sharper in activation assumptions: because the finite action-groupoid case reduces to finite-dimensional MLP approximation plus finite Reynolds averaging, it only assumes that α is continuous and non-polynomial.
<!-- anchor:TXT-0253 -->

Proof. The groupoid G ⋉ P is finite and discrete. Hence the CENN approximate identities are point masses, all convolution integrals are finite sums, arrow probes separate because identity arrows are present, and equivariant compilation is finite groupoid averaging. Therefore Theorem A.3 applies to X and Y .
<!-- anchor:TXT-0254 -->

The theorem is stated for global natural transformations, while OENN is stated on a compact invariant domain K . This causes no loss in the present finite-dimensional groupoid case. Given F ∈ C G ( K,Y tot ) , extend it coordinatewise by the Tietze extension theorem to a continuous map H : X tot → Y tot , and then Reynolds-symmetrize
<!-- anchor:TXT-0255 -->

$$
˜ F ( x ) := 1 | G | ∑ γ ∈ G ρ Y ( γ -1 ) H ( ρ X ( γ ) x ) .
$$
<!-- anchor:EQ-0126 -->

Then ˜ F is continuous and G -equivariant, and ˜ F | K = F because K is G -invariant and F is equivariant. Thus every compact-domain natural family extends to a global natural transformation of X into Y .
<!-- anchor:TXT-0256 -->

Applying the CENN UAT to this extension with F = P and K q = K for all q gives density on K by finite actiongroupoid CENN approximants. Proposition A.4 identifies the target space of natural families with C G ( K,Y tot ) and identifies the CENN compact-open finite-object seminorm with the OENN uniform norm on K . Lemma A.6 shows that the required finite approximants can be chosen to assemble to full OENN networks, while Proposition A.5 gives the primitive-level embedding of OENN layers into the finite CENN formalism; together they complete the comparison without requiring arbitrary CENN layers to be OENN primitives.
<!-- anchor:TXT-0257 -->

Remark A.8 (The poset category does not give the OENN embedding) . The thin category associated with P has a unique arrow p → q when p ≤ q . Naturality over this category imposes commutation with order arrows, such as restriction or incidence maps. OENN equivariance instead imposes
<!-- anchor:TXT-0258 -->

$$
F ( ρ X ( γ ) x ) = ρ Y ( γ ) F ( x ) ( γ ∈ G ) ,
$$
<!-- anchor:EQ-0127 -->

where G acts by order automorphisms. Thus the order relation determines useful G -stable masks, cover relations, pairstate communication graphs, and sheaf restriction structure, but the categorical symmetry behind a completed OENN input-output map is the action groupoid G ⋉ P . Hidden OENN primitives may additionally use auxiliary finite G -sets, such as P × P , and those primitives are typed over their own action groupoids. In short, OENN embeds into finite point-base CENN over the action groupoids G ⋉ S for the finite G -sets S appearing in the construction. Completed input-output maps are represented over G ⋉ P ; pair-state layers are represented over G ⋉ ( P × P ) ; Reynolds branch MLPs use finite branch-copy action groupoids; and locality is imposed by optional G -stable support constraints inherited from the poset.
<!-- anchor:TXT-0259 -->

## A.3. Experiments: CENN for Multimodal Learning
<!-- anchor:SEC-0024 -->

In CENN, a category serves as a generalized symmetry structure. In concrete machine learning tasks, we can exploit equivariance with respect to the compositional structure of symmetry categories. To represent richer symmetry structures, categories can be composed together in various manners. For example, product categories provide one way to realize such compositional symmetries (Maruyama, 2025b;c). More broadly, category theory offers systematic methods for composing mathematical structures, allowing us to leverage compositional symmetries in multimodal machine learning in particular as we explain below (Maruyama, 2026b; Maruyama and Yasuda, 2026).
<!-- anchor:TXT-0260 -->

Grothendieck CENN: integrating symmetries. The Grothendieck construction is a fundamental composition method in the theory of fibrations: it packages a family of categories that varies over a base context category into a single total category. Formally, given a functor valued in the category of small categories
<!-- anchor:TXT-0261 -->

$$
F : B op → Cat , (35)
$$
<!-- anchor:EQ-0128 -->

the Grothendieck construction produces the integrated category
<!-- anchor:TXT-0262 -->

$$
∫ b ∈B F ( b ) , (36)
$$
<!-- anchor:EQ-0129 -->

which is obtained by gluing the local categorical structures F ( b ) along the base context B . A Grothendieck CENN is a CENN that is equivariant with respect to this integrated category, enabling machine learning under a global composite symmetry assembled from context-dependent local symmetries .
<!-- anchor:TXT-0263 -->

EMG-IMU experiments and results. To test the performance of Grothendieck CENN, we consider the EMG-IMU benchmark (Khan et al., 2020b;a), where wearable devices collect both electromyography (EMG) signals and inertial measurement unit (IMU) signals, and the task is to classify actions or gestures from the resulting time-series data. EMG-IMU leverages multimodal signals. We compared GrothendieckCENN against TemporalCNN and InvariantTransformer. Table 2 shows the experimental results; GrothendieckCENN substantially outperformed both of them.
<!-- anchor:TXT-0264 -->

**Table:** [table on page 19]

Assets: assets/TAB-0003.json, assets/TAB-0003.csv
<!-- anchor:TAB-0003 -->

**Table:** Table 2. EMG-IMU: performance of Grothendieck CENN against the standard Temporal CNN baseline.

Assets: assets/TAB-0004.json, assets/TAB-0004.csv
<!-- anchor:TAB-0004 -->

Formal definition of Grothendieck category. Let B be a small category, called the base context category, and let F : B op → Cat be a contravariant functor. The Grothendieck construction ∫ b ∈B F ( b ) is the category defined as follows:
<!-- anchor:TXT-0265 -->

Objects are pairs ( b, x ) with b ∈ Ob( B ) and x ∈ Ob( F ( b )) .
<!-- anchor:TXT-0266 -->

An arrow ( b, x ) → ( b ′ , y ) is a pair ( f, φ ) where f : b → b ′ in B and φ : x → F ( f )( y ) in F ( b ) .
<!-- anchor:TXT-0267 -->

Composition is given by
<!-- anchor:TXT-0268 -->

$$
( g, ψ ) ◦ ( f, φ ) = ( g ◦ f, F ( f )( ψ ) ◦ φ ) .
$$
<!-- anchor:EQ-0130 -->

Thus ∫ b ∈B F ( b ) glues the fiber categories F ( b ) along the context arrows of B into one total category.
<!-- anchor:TXT-0269 -->

Intuition for this experiment. The Grothendieck category ∫ b ∈B F ( b ) is a global space that organizes, modality by modality, the allowed nuisance transformations, such as device-pose rotation, temporal misalignment, electrode reindexing, and gain drift. It assigns appropriate featureextraction rules as fibers and integrates only the information required for the final decision into a shared representation. Rather than merely concatenating modality embeddings, it specifies how modalities are glued together by declaring which nuisance transformations should be collapsed and which invariant signals should remain accessible to the classifier.
<!-- anchor:TXT-0270 -->

Context-dependent local symmetries. In multimodal sensing, the relevant symmetry is not a single global group acting everywhere: it depends on the modality . In our EMG-IMU setting, three groups play distinct roles:
<!-- anchor:TXT-0271 -->

cyclic time shifts C T := Z T , common to all modalities;
<!-- anchor:TXT-0272 -->

electrode ring shifts C 8 := Z 8 , used for EMG;
<!-- anchor:TXT-0273 -->

3D rotations SO(3) , used for IMU.
<!-- anchor:TXT-0274 -->

Equivalently, IMU streams carry SO(3) × C T symmetry, EMG carries C 8 × C T , and the fused representation keeps only C T , with rotation and electrode indexing intended to be forgotten after invariantization.
<!-- anchor:TXT-0275 -->

Base context category. To express this context-dependent symmetry structure, we use a base context category B whose objects are modality contexts such as ACC , GYR , EMG , and TOT and whose morphisms include the fusion arrows into TOT . Here ACC is the accelerometer modality, GYR is the gyroscope modality, EMG is the electromyography modality, and TOT is the fused total modality combining the streams. We integrate symmetries over the base context category B .
<!-- anchor:TXT-0276 -->

Integrating symmetries over contexts. We define an indexed family
<!-- anchor:TXT-0277 -->

$$
F : B op → Cat ,
$$
<!-- anchor:EQ-0131 -->

where each F ( b ) is the group symmetry category B ( G b ) encoding the local symmetry group G b at context b :
<!-- anchor:TXT-0278 -->

$$
G ACC = G GYR = SO(3) × C T , G EMG = C 8 × C T , G TOT = C T .
$$
<!-- anchor:EQ-0132 -->

On a fusion arrow i b : b → TOT , contravariance gives a functor F ( i b ) : B ( G TOT ) → B ( G b ) induced by the canonical inclusion of C T into G b , so the forgotten factor SO(3) or C 8 acts trivially at TOT . The Grothendieck construction
<!-- anchor:TXT-0279 -->

$$
∫ b ∈B F ( b )
$$
<!-- anchor:EQ-0133 -->

then integrates these varying local group actions into a single total category: equivariance of the network is realized as naturality over ∫ b ∈B F ( b ) , which simultaneously captures within-modality symmetries and their systematic change under fusion.
<!-- anchor:TXT-0280 -->

Why does Grothendieck CENN work well? Nuisance factors such as pose, temporal shift, and electrode placement are difficult to learn from limited data. Grothendieck CENN builds the relevant invariances into the representation via categorical equivariance. Otherwise models must acquire such invariances from data and can be misled by superficial differences under finite samples. In contrast, Grothendieck CENN extracts and fuses invariants that persist under these nuisance transformations, such as features insensitive to rotations and reindexings, allowing learning capacity to focus on class-specific structure. This yields improved generalization. For more on experimental evaluation, we refer to (Maruyama, 2025b;c; 2026a;b; Maruyama and Yasuda, 2026), which provide experimental results obtained via product category equivariance, Grothendieck category equivariance, and category-equivariant regularization methods.
<!-- anchor:TXT-0281 -->

## B. Proofs
<!-- anchor:SEC-0025 -->

This appendix provides the proofs of the results stated in Sections 2-4. The numbering below refers to the corresponding statements in the main text.
<!-- anchor:TXT-0282 -->

## B.1. Proofs for Section 2
<!-- anchor:SEC-0026 -->

Proof of Proposition 2.3. Using (1) and (3),
<!-- anchor:TXT-0283 -->

$$
( Lρ X ( γ ) x ) q = ∑ p ∈ P K ( q, p ) T V γ,γ -1 p x γ -1 p = ∑ r ∈ P K ( q, γr ) T V γ,r x r .
$$
<!-- anchor:EQ-0134 -->

On the other hand,
<!-- anchor:TXT-0284 -->

$$
( ρ Y ( γ ) Lx ) q = T W γ,γ -1 q ( Lx ) γ -1 q = ∑ r ∈ P T W γ,γ -1 q K ( γ -1 q, r ) x r .
$$
<!-- anchor:EQ-0135 -->

Equality for all x is equivalent to
<!-- anchor:TXT-0285 -->

$$
K ( q, γr ) T V γ,r = T W γ,γ -1 q K ( γ -1 q, r ) ( q, r ∈ P ) .
$$
<!-- anchor:EQ-0136 -->

Replacing q by γq gives (4). The converse is the same computation in reverse.
<!-- anchor:TXT-0286 -->

Proof of Proposition 2.4. If γ 1 ( q O , p O ) = γ 2 ( q O , p O ) , then η := γ -1 2 γ 1 ∈ H O . By functoriality and (5),
<!-- anchor:TXT-0287 -->

$$
T γ W 1 ,q O A O ( T V γ 1 ,p O ) -1 = T γ W 2 ,q O T W η,q O A O ( T V η,p O ) -1 ( T V γ 2 ,p O ) -1 = T γ W 2 ,q O A O ( T V γ 2 ,p O ) -1 .
$$
<!-- anchor:EQ-0137 -->

Thus (6) is well-defined. Substitution into (4) gives equivariance. Conversely, if L is equivariant, set A O := K ( q O , p O ) . Taking γ ∈ H O in (4) gives (5), and arbitrary γ gives (6). The dimension formula follows by the direct sum over pairorbits.
<!-- anchor:TXT-0288 -->

Proof of Lemma 2.8. Equivariance follows by the change of variables t = hg :
<!-- anchor:TXT-0289 -->

$$
R eq H [Ψ]( T U g u ) = 1 | H | ∑ h ∈ H ( T V h ) -1 Ψ( T U hg u ) = T V g R eq H [Ψ]( u ) .
$$
<!-- anchor:EQ-0138 -->

For the realization, write the MLP as
<!-- anchor:TXT-0290 -->

$$
Ψ( u ) = A L σ ( A L -1 σ ( · · · σ ( A 1 u + b 1 ) · · · ) + b L -1 ) + b L .
$$
<!-- anchor:EQ-0139 -->

For a hidden width n i , use the branch space E i = ( R n i ) H with right-regular action
<!-- anchor:TXT-0291 -->

$$
( π i ( g ) z ) h = z hg .
$$
<!-- anchor:EQ-0140 -->

The first affine map is
<!-- anchor:TXT-0292 -->

$$
( B 1 u ) h = A 1 T U h u + b 1 ,
$$
<!-- anchor:EQ-0141 -->

and the hidden affine maps are ( B i z ) h = A i z h + b i . These maps are H -equivariant, and coordinatewise σ is equivariant because H only permutes branches. The output map
<!-- anchor:TXT-0293 -->

$$
Cz = 1 | H | ∑ h ∈ H ( T V h ) -1 ( A L z h + b L )
$$
<!-- anchor:EQ-0142 -->

is affine and H -equivariant. The branch indexed by h computes Ψ( T U h u ) , so the resulting network computes (7).
<!-- anchor:TXT-0294 -->

Proof of Lemma 2.12. If ( q, p ) = γ ( q O , p O ) , then ( τq, τp ) = τγ ( q O , p O ) . Hence
<!-- anchor:TXT-0295 -->

$$
φ τq,τp ( T V τ,p v ) = φ O ( ( T V τγ,p O ) -1 T V τ,p v ) = φ O ( ( T V γ,p O ) -1 v ) = φ q,p ( v ) .
$$
<!-- anchor:EQ-0143 -->

The map p ↦→ τp bijects the terms in the sum defining S O ( q ; x ) with those defining S O ( τq ; ρ X ( τ ) x ) .
<!-- anchor:TXT-0296 -->

Proof of Proposition 2.13. Well-definedness in the choice of γ follows from G q 0 -equivariance of ψ q 0 and Lemma 2.12. Equivariance follows by replacing q = γq 0 with τq = ( τγ ) q 0 and using the same lemma.
<!-- anchor:TXT-0297 -->

For the realization, let S = P × P with the diagonal G -action and define an auxiliary bundle ̂ Z over S by
<!-- anchor:TXT-0298 -->

$$
̂ Z ( q,p ) := V p , T ̂ Z τ, ( q,p ) := T V τ,p : ̂ Z ( q,p ) → ̂ Z ( τq,τp ) .
$$
<!-- anchor:EQ-0144 -->

Define the pair-lift
<!-- anchor:TXT-0299 -->

$$
B : X → ⊕ ( q,p ) ∈ P × P ̂ Z ( q,p ) , ( Bx ) ( q,p ) := x p .
$$
<!-- anchor:EQ-0145 -->

It is an orbital linear map: for every τ ∈ G ,
<!-- anchor:TXT-0300 -->

$$
( Bρ X ( τ ) x ) ( q,p ) = T V τ,τ -1 p x τ -1 p = ( ρ ̂ Z ( τ ) Bx ) ( q,p ) .
$$
<!-- anchor:EQ-0146 -->

For each pair-orbit O , restrict ̂ Z to O and apply the pointwise Reynolds layer whose representative block is the invariant block φ O : V p O → R m O , with trivial transports on the output fibers. By (9), this produces pair features
<!-- anchor:TXT-0301 -->

$$
u O ( q,p ) = φ q,p ( x p ) (( q, p ) ∈ O ) .
$$
<!-- anchor:EQ-0147 -->

Next define the summary bundle M O over P by M O q = R m O with trivial transports, and use the orbital linear summation map
<!-- anchor:TXT-0302 -->

$$
( A O u ) q := ∑ p ∈ P ( q,p ) ∈O u ( q,p ) .
$$
<!-- anchor:EQ-0148 -->

Its support is the G -stable relation { ( q, ( q, p )) : ( q, p ) ∈ O} ⊂ P ×O , and its nonzero kernels are identities, so it satisfies the auxiliary transporter law. Hence A O u is exactly the summary S O ( q ; x ) .
<!-- anchor:TXT-0303 -->

Finally, concatenate the identity skip x q ∈ V q with all summaries belonging to
<!-- anchor:TXT-0304 -->

$$
A ( q ) := {O : ∃ p ∈ P with ( q, p ) ∈ O} .
$$
<!-- anchor:EQ-0149 -->

This gives an equivariant bundle E over P with
<!-- anchor:TXT-0305 -->

$$
E q := V q ⊕ ⊕ O∈A ( q ) R m O ,
$$
<!-- anchor:EQ-0150 -->

where transports act as T V on V q and trivially on the summary coordinates. The final map with representative blocks ψ q 0 is a pointwise Reynolds layer E → W , and it computes (12). Therefore F is a finite composition of OENN primitives.
<!-- anchor:TXT-0306 -->

Proof of Proposition 2.15. The first claim is Proposition 2.13. For the approximation claim, apply the finitegroup density lemma, Lemma 3.2, to each stabilizerinvariant encoder and each stabilizer-equivariant readout on the finitely many orbit representatives. Since the number of orbits and sites is finite, the resulting errors compose continuously and can be chosen small enough to give uniform approximation on the prescribed compact set.
<!-- anchor:TXT-0307 -->

Proof of Proposition 2.16. The first inclusion is realized locally as follows. Given a relation-message-passing layer of the form (13), first write the input into a pair-state diagonal seed
<!-- anchor:TXT-0308 -->

̸
<!-- anchor:TXT-0309 -->

$$
z 0 q,p := { h q , p = q, 0 , p = q,
$$
<!-- anchor:EQ-0151 -->

which is a carrier-diagonal write map from the P -indexed state to the P × P -indexed pair-state bundle. Then apply one source-preserving pair-state R -local propagation
<!-- anchor:TXT-0310 -->

$$
z 1 q,p := ∑ r :( q,r ) ∈ R z 0 r,p .
$$
<!-- anchor:EQ-0152 -->

Since z 0 r,p is nonzero only when r = p , this gives z 1 q,p = h p for ( q, p ) ∈ R and z 1 q,p = 0 otherwise. Thus the apparent off-diagonal lift is implemented by an allowed diagonal seed followed by one pair-state local propagation. Apply the transported invariant encoders slotwise on the relevant pair-orbits O ⊆ R , sum the resulting features over source slots at fixed carrier q by a carrier-local affine map, and apply the carrier-local Reynolds readout θ q . Thus every relationmessage-passing layer belongs to OENN R -pair σ . The second inclusion follows because pair-state bundles are auxiliary finite G -set bundles allowed in the full OENN class, and R -local masks are special orbital masks.
<!-- anchor:TXT-0311 -->

## B.2. Proofs for Section 3
<!-- anchor:SEC-0027 -->

Proof of Lemma 3.1. This is the q -coordinate of F ( ρ X ( η ) x ) = ρ Y ( η ) F ( x ) ; since ηq = q , the q -coordinate of ρ Y ( η ) y is T W η,q y q .
<!-- anchor:TXT-0312 -->

Proof of Lemma 3.2. Fix the norm ‖ · ‖ ∗ appearing in the statement. Choose an H -invariant inner product on V by averaging any inner product over H , and let ‖ · ‖ 0 be its norm. Then every T V h is an isometry for ‖ · ‖ 0 . Since V is finite-dimensional, there is a constant c > 0 such that
<!-- anchor:TXT-0313 -->

$$
‖ v ‖ ∗ ≤ c ‖ v ‖ 0 ( v ∈ V ) .
$$
<!-- anchor:EQ-0153 -->

The standard finite-dimensional MLP universal approximation theorem applies to scalar continuous functions on compact boxes. For vector-valued f , apply the scalar theorem coordinatewise in a basis of V ; for an arbitrary compact set K ⊂ U , first extend each coordinate continuously to a compact box containing K by the Tietze extension theorem. Thus, for the continuous non-polynomial activation σ (Leshno et al., 1993), choose Ψ with
<!-- anchor:TXT-0314 -->

$$
sup u ∈ K ‖ Ψ( u ) -f ( u ) ‖ 0 < ε/c.
$$
<!-- anchor:EQ-0154 -->

The Reynolds average ψ is H -equivariant by Lemma 2.8. For u ∈ K ,
<!-- anchor:TXT-0315 -->

$$
ψ ( u ) -f ( u ) = 1 | H | ∑ h ∈ H ( T V h ) -1 ( Ψ( T U h u ) -f ( T U h u ) ) ,
$$
<!-- anchor:EQ-0155 -->

because f ( T U h u ) = T V h f ( u ) . Since K is H -invariant and the T V h are isometries for ‖ · ‖ 0 , the ‖ · ‖ 0 -norm of the right-hand side is at most ε/c . Therefore
<!-- anchor:TXT-0316 -->

$$
sup u ∈ K ‖ ψ ( u ) -f ( u ) ‖ ∗ < ε.
$$
<!-- anchor:EQ-0156 -->

This proves the density statement for the original norm. The branch realization is Lemma 2.8.
<!-- anchor:TXT-0317 -->

Proof of Theorem 3.3. Fix f ∈ C G ( K,Y ) and ε > 0 . Choose norms on each W q and use the max norm ‖ y ‖ Y =
<!-- anchor:TXT-0318 -->

max q ‖ y q ‖ W q . Let Q ⊂ P be a set of site-orbit representatives. For q 0 ∈ Q , define
<!-- anchor:TXT-0319 -->

$$
g q 0 : K → W q 0 , g q 0 ( x ) = f ( x ) q 0 .
$$
<!-- anchor:EQ-0157 -->

By Lemma 3.1, g q 0 is G q 0 -equivariant.
<!-- anchor:TXT-0320 -->

Let
<!-- anchor:TXT-0321 -->

$$
C := max ( 1 , max γ ∈ G, q 0 ∈Q ‖ T W γ,q 0 ‖ op ) ,
$$
<!-- anchor:EQ-0158 -->

computed with the chosen norms. Set δ = ε/C . Applying Lemma 3.2 with H = G q 0 , U = X , V = W q 0 , the norm ‖ · ‖ W q 0 , and K gives a Reynolds block
<!-- anchor:TXT-0322 -->

$$
ψ q 0 : X → W q 0
$$
<!-- anchor:EQ-0159 -->

such that ψ q 0 is G q 0 -equivariant and
<!-- anchor:TXT-0323 -->

$$
sup x ∈ K ‖ ψ q 0 ( x ) -g q 0 ( x ) ‖ W q 0 < δ. (37)
$$
<!-- anchor:EQ-0160 -->

For q = γq 0 , define
<!-- anchor:TXT-0324 -->

$$
ψ q ( x ) := T W γ,q 0 ψ q 0 ( ρ X ( γ -1 ) x ) . (38)
$$
<!-- anchor:EQ-0161 -->

This is independent of the chosen γ . Indeed, if γq 0 = γ ′ q 0 , then η = γ ′-1 γ ∈ G q 0 and γ = γ ′ η . For v = ρ X ( γ ′-1 ) x , G q 0 -equivariance gives
<!-- anchor:TXT-0325 -->

$$
T W η,q 0 ψ q 0 ( ρ X ( η -1 ) v ) = ψ q 0 ( v ) ,
$$
<!-- anchor:EQ-0162 -->

which implies equality of the two definitions.
<!-- anchor:TXT-0326 -->

Define F : X → Y by F ( x ) q = ψ q ( x ) . If q = γq 0 and τ ∈ G , then τq = ( τγ ) q 0 , so
<!-- anchor:TXT-0327 -->

$$
F ( ρ X ( τ ) x ) τq = T W τγ,q 0 ψ q 0 ( ρ X ( γ -1 ) x ) = T W τ,q F ( x ) q .
$$
<!-- anchor:EQ-0163 -->

Thus F is order-equivariant.
<!-- anchor:TXT-0328 -->

For x ∈ K and q = γq 0 , equivariance of f gives
<!-- anchor:TXT-0329 -->

$$
f ( x ) q = T W γ,q 0 g q 0 ( ρ X ( γ -1 ) x ) .
$$
<!-- anchor:EQ-0164 -->

Since K is G -invariant, ρ X ( γ -1 ) x ∈ K , and (37) gives
<!-- anchor:TXT-0330 -->

$$
‖ F ( x ) q -f ( x ) q ‖ W q ≤ ‖ T W γ,q 0 ‖ op δ ≤ Cδ = ε.
$$
<!-- anchor:EQ-0165 -->

Taking the maximum over q gives ‖ F ( x ) -f ( x ) ‖ Y ≤ ε on K .
<!-- anchor:TXT-0331 -->

It remains to verify that F is a full OENN. Let ˜ X be the bundle over P with fiber ˜ X q = X and transport T ˜ X γ,q = ρ X ( γ ) . The broadcast map
<!-- anchor:TXT-0332 -->

$$
B : X → ⊕ q ∈ P ˜ X q , ( Bx ) q = x, (39)
$$
<!-- anchor:EQ-0166 -->

is orbital linear; indeed Bρ X ( γ ) = ρ ˜ X ( γ ) B follows immediately from T ˜ X γ,q = ρ X ( γ ) . The pointwise map N : ˜ X → Y defined by ( Nz ) q = ψ q ( z q ) is a pointwise Reynolds layer by Definition 2.9. Hence F = N ◦ B belongs to OENN full σ ( X,Y ) . This proves density.
<!-- anchor:TXT-0333 -->

Proof of Corollary 3.4. This is the specialization of Theorem 3.3 to trivial original fiber transports. Corollary 2.5 identifies the linear layers with pair-orbit tying, and Lemma 2.8 realizes the finite stabilizer averages needed for equivariant readouts.
<!-- anchor:TXT-0334 -->

Proof of Theorem 3.5. The dependency claim in the lower bound is an induction on the number of inter-site layers. It is true at depth zero because each site contains only its own input. A pointwise map, a carrier-diagonal equivariant map, or a concatenation does not enlarge the dependency set. An R -local inter-site layer can enlarge the dependency set of site q only by one reverse step along an incoming edge r → q of Γ R . Hence after L such layers, site q can depend only on the radiusL in-neighborhood of q .
<!-- anchor:TXT-0335 -->

If d R ( p, q ) > L , the approximant's q -coordinate is independent of x p . Choose two points of [0 , 1] P that differ only in the p -coordinate, with values 0 and 1 . The approximant has the same q -output on both points, while the target outputs differ by 1 . Therefore the uniform error is at least 1 / 2 for one of the two points.
<!-- anchor:TXT-0336 -->

It remains to prove the diameter-depth compilation. Let Z be the equivariant bundle over the pair-state set P × P defined by
<!-- anchor:TXT-0337 -->

$$
Z ( q,p ) := V p , T Z γ, ( q,p ) := T V γ,p : Z ( q,p ) → Z ( γq,γp ) .
$$
<!-- anchor:EQ-0167 -->

Equivalently, the carrier site q stores the source-indexed memory E q = ⊕ p ∈ P V p , and G sends the p -slot over q to the γp -slot over γq .
<!-- anchor:TXT-0338 -->

First seed each source into its own labeled slot by the diagonal map I : X → Z ,
<!-- anchor:TXT-0339 -->

̸
<!-- anchor:TXT-0340 -->

$$
( Ix ) q,p := { x p , q = p, 0 , q = p.
$$
<!-- anchor:EQ-0168 -->

This support is G -stable and carrier-local. Next define the carrierR -local propagation operator M : Z → Z by
<!-- anchor:TXT-0341 -->

$$
( Mz ) q,p := ∑ r ∈ P ( q,r ) ∈ R z r,p .
$$
<!-- anchor:EQ-0169 -->

Its kernel blocks satisfy
<!-- anchor:TXT-0342 -->

$$
K (( q, p ) , ( r, s )) = 0 unless s = p and ( q, r ) ∈ R,
$$
<!-- anchor:EQ-0170 -->

so M is pair-state R -local in the sense of Definition 2.11. Since R is G -invariant and the p -slot is transported to the γp -slot by T V γ,p , the nonzero block kernels of M also satisfy the auxiliary transporter law. Hence M is a pair-state R -local orbital linear layer.
<!-- anchor:TXT-0343 -->

For every q, p ∈ P ,
<!-- anchor:TXT-0344 -->

$$
( M D Ix ) q,p = a q,p x p ,
$$
<!-- anchor:EQ-0171 -->

where a q,p is the number of directed lengthD walks from p to q in Γ R . Because R contains the diagonal, walks can be padded by self-loops; since D is the directed diameter and Γ R is strongly connected, a q,p > 0 for all q, p . The G -invariance of R gives
<!-- anchor:TXT-0345 -->

$$
a γq,γp = a q,p ( γ ∈ G ) .
$$
<!-- anchor:EQ-0172 -->

Therefore the pairwise diagonal rescaling S : Z → Z defined by
<!-- anchor:TXT-0346 -->

$$
( Sz ) q,p := a -1 q,p z q,p
$$
<!-- anchor:EQ-0173 -->

satisfies the transporter law and is carrier-local. Now ( SM D Ix ) q,p = x p for all q, p .
<!-- anchor:TXT-0347 -->

Finally collect the pair-state slots at each carrier site by the carrier-local equivariant map C : Z → ⊕ q ∈ P ˜ X q ,
<!-- anchor:TXT-0348 -->

$$
( Cz ) q = ( z q,p ) p ∈ P ∈ ⊕ p ∈ P V p = X.
$$
<!-- anchor:EQ-0174 -->

The transports on Z and ˜ X make C equivariant. Hence CSM D I = B , proving that the broadcast is exactly compiled by D pair-state local inter-site propagation layers plus carrier-local seed, rescaling, and collection maps.
<!-- anchor:TXT-0349 -->

The universality assertion follows from the proof of Theorem 3.3, which constructs an approximant F = N ◦ B , where B is the broadcast layer and N is pointwise. The broadcast B has just been exactly realized by pair-state R -local primitives, and N is a pointwise Reynolds layer, hence uses no inter-site communication. Therefore the same approximant belongs to OENN R -pair σ ( X,Y ) . If L < D , the definition of directed diameter gives sites p, q with d R ( p, q ) > L , so the lower-bound part gives the stated sharpness.
<!-- anchor:TXT-0350 -->

Proof of Corollary 3.6. The relation R cov is G -invariant because G acts by order automorphisms and therefore preserves cover relations. Its communication graph is the selflooped directed version of the undirected Hasse graph with both orientations on every cover edge. Connectedness of the undirected Hasse graph is therefore equivalent to strong connectedness of this communication graph. Apply Theorem 3.5.
<!-- anchor:TXT-0351 -->

## B.3. Proofs for Section 4
<!-- anchor:SEC-0028 -->

Proof of Lemma 4.1. Choose one representative p 0 in each G -orbit of cells. Average any inner product on V p 0 over the stabilizer G p 0 , and transport this inner product to V γp 0 by declaring T V γ,p 0 to be an isometry. The stabilizer invariance makes the definition independent of the chosen γ , and the cocycle identity for T V makes all transports isometries.
<!-- anchor:TXT-0352 -->

Taking Hilbert adjoints in (20) gives
<!-- anchor:TXT-0353 -->

$$
R ∗ p → q ( T V γ,q ) -1 = ( T V γ,p ) -1 R ∗ γp → γq ,
$$
<!-- anchor:EQ-0175 -->

because the transports are isometries. Multiplying by T V γ,p on the left and by T V γ,q on the right gives (21).
<!-- anchor:TXT-0354 -->

Proof of Lemma 4.2. The self terms are precisely the diagonal pair-orbit case of Proposition 2.4, so they satisfy (4).
<!-- anchor:TXT-0355 -->

For the upward terms, if ( q, p ) = α ( q O , p O ) , then
<!-- anchor:TXT-0356 -->

$$
K ↑ ( q, p ) = T W α,q O B ↑ O R p O → q O ( T V α,p O ) -1 .
$$
<!-- anchor:EQ-0176 -->

For any γ ∈ G , the kernel at ( γq, γp ) is obtained by using γα as transporter. Hence, by functoriality,
<!-- anchor:TXT-0357 -->

$$
K ↑ ( γq, γp ) T V γ,p = T W γα,q O B ↑ O R p O → q O ( T V γα,p O ) -1 T V γ,p = T W γ,q K ↑ ( q, p ) .
$$
<!-- anchor:EQ-0177 -->

The downward calculation is the same, using the adjoint naturality (21). In the globally shared notation below, this calculation reduces to
<!-- anchor:TXT-0358 -->

$$
B ↑ R γp → γq T V γ,p = B ↑ T V γ,q R p → q ,
$$
<!-- anchor:EQ-0178 -->

which equals T W γ,q B ↑ R p → q precisely when the shared block B ↑ intertwines the relevant transports; this is automatic in the permutation-only case. Therefore all kernels in (22) satisfy the transporter law, and the layer is order-equivariant by Proposition 2.3.
<!-- anchor:TXT-0359 -->
